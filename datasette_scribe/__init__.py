from datasette import hookimpl, Response
from datasette.database import Database
import httpx
import json
import asyncio
from pathlib import Path
from ulid import ULID
import random

SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text()


async def bg_task(datasette, db, job_id, url):
    BASE_URL = datasette.plugin_config("datasette-scribe").get("BASE_URL")

    while True:
        await asyncio.sleep(random.uniform(2.0, 5.0))
        try:
            response = (
                httpx.get(f"{BASE_URL}/status/" + job_id).raise_for_status().json()
            )
        except httpx.HTTPStatusError as e:
            print(e)

            def errored(db):
                with db:
                    db.execute(
                        """
                          UPDATE datasette_scribe_submitted_jobs
                          SET completed_at = datetime('now'),
                            status = 'failed'
                          WHERE id = ?
                        """,
                        [job_id],
                    )

            await db.execute_write_fn(errored)
            return

        if response.get("completed"):
            transcript = response.get("transcript")
            video_title = response.get("video_title")
            video_duration_seconds = response.get("video_duration_seconds")

            def completed(db):
                with db:
                    transcript_id = str(ULID()).lower()
                    db.execute(
                        """
                          UPDATE datasette_scribe_submitted_jobs
                          SET completed_at = datetime('now'),
                            status = 'completed'
                          WHERE id = ?
                        """,
                        [job_id],
                    )
                    db.execute(
                        """
                          INSERT INTO datasette_scribe_transcripts(id, job_id, url, title, duration, meta)
                          VALUES (?, ?, ?, ?, ?, NULL)
                        """,
                        [
                            transcript_id,
                            job_id,
                            url,
                            video_title,
                            video_duration_seconds,
                        ],
                    )
                    transcript_entries = list(
                        map(
                            lambda d: {
                                "transcript_id": transcript_id,
                                "speaker": d.get("speaker"),
                                "started_at": d.get("timestamp")[0],
                                "ended_at": d.get("timestamp")[1],
                                "contents": d.get("text"),
                            },
                            transcript,
                        )
                    )
                    db.executemany(
                        """
                          INSERT INTO datasette_scribe_transcription_entries(transcript_id, speaker, started_at, ended_at, contents)
                          VALUES(:transcript_id, :speaker, :started_at, :ended_at, :contents)
                        """,
                        transcript_entries,
                    )

            await db.execute_write_fn(completed)
            return
        if response.get("error"):

            def errored(db):
                with db:
                    db.execute(
                        """
                          UPDATE datasette_scribe_submitted_jobs
                          SET completed_at = datetime('now'),
                            status = 'failed'
                          WHERE id = ?
                        """,
                        [job_id],
                    )

            await db.execute_write_fn(errored)
            return
        print(job_id, response)


@hookimpl
async def startup(datasette):
    for name, db in datasette.databases.items():
        if db.is_mutable:
            await db.execute_write_script(SCHEMA_SQL)


@hookimpl
def menu_links(datasette, actor):
    return [
        {
            "href": datasette.urls.path("/-/datasette-scribe"),
            "label": "Scribe",
        },
    ]


class Routes:
    async def landing_view(scope, receive, datasette, request):
        databases = datasette.databases.keys()
        return Response.html(
            await datasette.render_template(
                "landing.html", context={"databases": databases}
            )
        )

    async def transcript_view(scope, receive, datasette, request):
        database = request.url_vars["database"]
        transcript_id = request.url_vars["transcript_id"]
        return Response.html(
            await datasette.render_template(
                "transcript.html",
                context={"transcript_id": transcript_id, "database": database},
            )
        )

    async def collection_view(scope, receive, datasette, request):
        database = request.url_vars["database"]
        collection_id = request.url_vars["collection_id"]
        return Response.html(
            await datasette.render_template(
                "collection.html",
                context={"collection_id": collection_id, "database": database},
            )
        )

    async def api_transcript(scope, receive, datasette, request):
        db_name = request.url_vars["database"]
        transcript_id = request.url_vars["transcript_id"]

        db = datasette.databases.get(db_name)
        if not db:
            return Response.json({}, status=400)
        transcript = (
            await db.execute(
                """
              with collections as (
                SELECT
                  transcript_id,
                  json_group_array(
                    json_object(
                      'collection_id', members.collection_id,
                      'name', collections.name
                    )
                  ) as collections
                FROM datasette_scribe_collection_members as members
                LEFT JOIN datasette_scribe_collections as collections on collections.key = members.collection_id
                WHERE transcript_id = ?1
              )
              SELECT
                transcripts.id,
                transcripts.job_id,
                transcripts.duration,
                transcripts.title,
                transcripts.url,
                collections.collections
              FROM datasette_scribe_transcripts as transcripts
              LEFT JOIN collections on collections.transcript_id = transcripts.id
              WHERE id = ?1
            """,
                [transcript_id],
            )
        ).first()
        transcript = dict(transcript)
        transcript["collections"] = json.loads(transcript["collections"] or "[]")

        entries = await db.execute(
            """
              SELECT
                entries.*
              FROM datasette_scribe_transcription_entries AS entries
              WHERE transcript_id = ?
            """,
            [transcript_id],
        )

        return Response.json(
            {"entries": [dict(row) for row in entries], "transcript": transcript}
        )

    async def api_collection(scope, receive, datasette, request):
        db_name = request.url_vars["database"]
        collection_id = request.url_vars["collection_id"]

        db = datasette.databases.get(db_name)
        if not db:
            return Response.json({}, status=400)
        collection = (
            await db.execute(
                """
              SELECT
                *
              FROM datasette_scribe_collections as collections
              WHERE key = ?1
            """,
                [collection_id],
            )
        ).first()

        transcripts = await db.execute(
            """
              SELECT
                transcripts.id,
                transcripts.title,
                transcripts.duration
              FROM datasette_scribe_collection_members AS members
              LEFT JOIN datasette_scribe_transcripts AS transcripts ON transcripts.id = members.transcript_id
              WHERE collection_id = ?
            """,
            [collection_id],
        )

        return Response.json(
            {
                "collection": dict(collection),
                "transcripts": [dict(row) for row in transcripts],
            }
        )

    async def api_jobs(scope, receive, datasette, request):
        db_name = request.url_vars["database"]
        db = datasette.databases.get(db_name)
        if not db:
            return Response.json({}, status=400)
        completed_jobs = await db.execute(
            """
              select
                jobs.id,
                transcripts.id as transcript_id,
                jobs.url,
                jobs.submitted_at,
                jobs.completed_at,
                transcripts.title,
                transcripts.duration,
                (
                  select
                    json_group_array(
                      json_object(
                        'collection_id', collection_id,
                        'name', collections.name
                      )
                    )
                  from datasette_scribe_collection_members as members
                  left join datasette_scribe_collections as collections on collections.key = members.collection_id
                  where transcript_id = transcripts.id
                ) as collections,
                (
                  select json_object(
                    'total_entries', count(*),
                    'total_speakers', count(distinct entries.speaker)
                  )
                  from datasette_scribe_transcription_entries as entries
                  where transcript_id = transcripts.id
                ) as entries_info
              from datasette_scribe_submitted_jobs as jobs
              left join datasette_scribe_transcripts as transcripts on transcripts.job_id = jobs.id
              where jobs.status = "completed"
              order by submitted_at desc
              limit 10
            """
        )
        inprogress_jobs = await db.execute(
            """
              SELECT jobs.*
              FROM datasette_scribe_submitted_jobs AS jobs
              WHERE status = 'pending'
              LIMIT 20
            """
        )

        def completed_job(row):
            d = dict(row)
            d["collections"] = json.loads(row["collections"])
            return d

        return Response.json(
            {
                "completed_jobs": [completed_job(row) for row in completed_jobs],
                "inprogress_jobs": [dict(row) for row in inprogress_jobs],
            }
        )

    async def api_collection_add_video(scope, receive, datasette, request):
        if request.method != "POST":
            return Response.text("", status=405)

        data = json.loads((await request.post_body()).decode("utf8"))
        db_name = data.get("database")
        collection_id = data.get("collection_id")
        transcript_id = data.get("transcript_id")

        db = datasette.databases.get(db_name)
        if not db:
            return Response.text("", status=400)

        def add_video_to_collection(db):
            with db:
                db.execute(
                    """
                      INSERT INTO datasette_scribe_collection_members(collection_id, transcript_id)
                      VALUES (?, ?)
                    """,
                    [collection_id, transcript_id],
                )

        await db.execute_write_fn(add_video_to_collection)
        return Response.json({})

    async def api_collection_remove_video(scope, receive, datasette, request):
        if request.method != "POST":
            return Response.text("", status=405)

        data = json.loads((await request.post_body()).decode("utf8"))
        db_name = data.get("database")
        collection_id = data.get("collection_id")
        transcript_id = data.get("transcript_id")

        db = datasette.databases.get(db_name)
        if not db:
            return Response.text("", status=400)

        def add_video_to_collection(db):
            with db:
                db.execute(
                    """
                      DELETE FROM datasette_scribe_collection_members
                      WHERE collection_id = ? AND transcript_id = ?
                    """,
                    [collection_id, transcript_id],
                )

        await db.execute_write_fn(add_video_to_collection)
        return Response.json({})

    async def api_collections(scope, receive, datasette, request):
        db_name = request.url_vars["database"]
        db = datasette.databases.get(db_name)
        if not db:
            return Response.json({}, status=400)
        collections = await db.execute(
            """
              WITH members AS (
                SELECT
                  collection_id,
                  count(transcript_id) as transcript_count
                FROM datasette_scribe_collection_members
                GROUP BY 1
              )
              SELECT
                key,
                name,
                description,
                members.transcript_count
              FROM datasette_scribe_collections as collections
              LEFT JOIN members ON members.collection_id = collections.key

            """
        )
        return Response.json([dict(row) for row in collections])

    async def api_collection_new(scope, receive, datasette, request):
        if request.method != "POST":
            return Response.text("", status=405)

        data = json.loads((await request.post_body()).decode("utf8"))
        db_name = data.get("database")
        name = data.get("name")
        description = data.get("description")

        db = datasette.databases.get(db_name)
        if not db:
            return Response.text("", status=400)

        if not name.strip():
            return Response.json({"message": "Name is required"}, status=400)

        def add_collection(db):
            with db:
                db.execute(
                    """
              INSERT INTO datasette_scribe_collections(key, name, description)
              VALUES (?, ?, ?)
            """,
                    [str(ULID()).lower(), name, description],
                )

        await db.execute_write_fn(add_collection)

        return Response.json({})

    async def api_search_collection(scope, receive, datasette, request):
        if request.method != "POST":
            return Response.text("", status=405)

        data = json.loads((await request.post_body()).decode("utf8"))
        db_name = data.get("database")
        collection_id = data.get("collection_id")
        query = data.get("query")

        db = datasette.databases.get(db_name)
        if not db:
            return Response.text("", status=400)
        print(collection_id, query)
        search_results = await db.execute(
            """
              SELECT
                entries.transcript_id,
                transcripts.title as video_title,
                transcripts.url as video_url,
                speaker,
                started_at,
                entries.contents,
                highlight(
                  datasette_scribe_transcription_entries_fts,
                  0,
                  '<strong>',
                  '</strong>'
                ) AS highlighted_contents
              FROM datasette_scribe_transcription_entries_fts AS entries_fts
              LEFT JOIN datasette_scribe_transcription_entries AS entries ON entries.rowid = entries_fts.rowid
              LEFT JOIN datasette_scribe_transcripts AS transcripts ON transcripts.id = entries.transcript_id
              WHERE entries_fts.contents MATCH :query
                AND entries_fts.transcript_id IN (
                  SELECT transcript_id
                  FROM datasette_scribe_collection_members
                  WHERE collection_id = :collection_id
                )
              ORDER BY rank
              LIMIT 20;
            """,
            params={"collection_id": collection_id, "query": query},
        )
        return Response.json({"results": [dict(row) for row in search_results]})

    async def api_submit(scope, receive, datasette, request):
        BASE_URL = datasette.plugin_config("datasette-scribe").get("BASE_URL")

        if request.method != "POST":
            return Response.text("", status=405)

        data = json.loads((await request.post_body()).decode("utf8"))
        urls = data.get("urls")
        db_name = data.get("database")
        actor_id = (request.actor and request.actor.get("id")) or None

        db = datasette.databases.get(db_name)
        if not db:
            return Response.text("", status=400)

        loop = asyncio.get_running_loop()
        job_ids = []
        for url in urls:
            job_id = str(ULID()).lower()
            job_ids.append(job_id)

            def add_job(db):
                with db:
                    db.execute(
                        """
                      INSERT INTO datasette_scribe_submitted_jobs(id, submitter_actor_id, submitted_at, url, status)
                      VALUES (?, ?, datetime('now'), ?, 'pending')
                    """,
                        [job_id, actor_id, url],
                    )

            await db.execute_write_fn(add_job)
            httpx.post(
                f"{BASE_URL}/submit", json={"id": job_id, "url": url}, timeout=30.0
            ).raise_for_status()
            loop.create_task(bg_task(datasette, db, job_id, url))

        return Response.json({"job_ids": job_ids})


@hookimpl
def register_routes():
    return [
        # views
        (r"^/-/datasette-scribe$", Routes.landing_view),
        (
            r"^/-/datasette-scribe/transcripts/(?P<database>.*)/(?P<transcript_id>.*)$",
            Routes.transcript_view,
        ),
        (
            r"^/-/datasette-scribe/collection/(?P<database>.*)/(?P<collection_id>.*)$",
            Routes.collection_view,
        ),
        (r"^/-/datasette-scribe/api/submit$", Routes.api_submit),
        (r"^/-/datasette-scribe/api/jobs/(?P<database>.*)$", Routes.api_jobs),
        (
            r"^/-/datasette-scribe/api/collections/(?P<database>.*)$",
            Routes.api_collections,
        ),
        (
            r"^/-/datasette-scribe/api/collection/new$",
            Routes.api_collection_new,
        ),
        (
            r"^/-/datasette-scribe/api/collection/add_video$",
            Routes.api_collection_add_video,
        ),
        (
            r"^/-/datasette-scribe/api/collection/remove_video$",
            Routes.api_collection_remove_video,
        ),
        (
            r"^/-/datasette-scribe/api/collection/search$",
            Routes.api_search_collection,
        ),
        (
            r"^/-/datasette-scribe/api/transcripts/(?P<database>.*)/(?P<transcript_id>.*)$",
            Routes.api_transcript,
        ),
        (
            r"^/-/datasette-scribe/api/collection/(?P<database>.*)/(?P<collection_id>.*)$",
            Routes.api_collection,
        ),
    ]
