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
    async def landing(scope, receive, datasette, request):
        databases = datasette.databases.keys()
        return Response.html(
            await datasette.render_template(
                "landing.html", context={"databases": databases}
            )
        )

    async def transcript(scope, receive, datasette, request):
        database = request.url_vars["database"]
        transcript_id = request.url_vars["transcript_id"]
        return Response.html(
            await datasette.render_template(
                "transcript.html",
                context={"transcript_id": transcript_id, "database": database},
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
              SELECT *
              FROM datasette_scribe_transcripts
              WHERE id = ?
            """,
                [transcript_id],
            )
        ).first()
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
            {"entries": [dict(row) for row in entries], "transcript": dict(transcript)}
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
        return Response.json(
            {
                "completed_jobs": [dict(row) for row in completed_jobs],
                "inprogress_jobs": [dict(row) for row in inprogress_jobs],
            }
        )

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
        (r"^/-/datasette-scribe$", Routes.landing),
        (
            r"^/-/datasette-scribe/transcripts/(?P<database>.*)/(?P<transcript_id>.*)$",
            Routes.transcript,
        ),
        (r"^/-/datasette-scribe/api/submit$", Routes.api_submit),
        (r"^/-/datasette-scribe/api/jobs/(?P<database>.*)$", Routes.api_jobs),
        (
            r"^/-/datasette-scribe/api/transcripts/(?P<database>.*)/(?P<transcript_id>.*)$",
            Routes.api_transcript,
        ),
    ]
