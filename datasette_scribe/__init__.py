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
                          VALUES (?, ?, ?, NULL, NULL, NULL)
                        """,
                        [transcript_id, job_id, url],
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

    async def api_jobs(scope, receive, datasette, request):
        db_name = request.url_vars["database"]
        db = datasette.databases.get(db_name)
        if not db:
            return Response.json({}, status=400)
        result = await db.execute(
            """
              select
                jobs.*,
                transcripts.id as transcript_id
              from datasette_scribe_submitted_jobs as jobs
              left join datasette_scribe_transcripts as transcripts on transcripts.job_id = jobs.id
              order by submitted_at desc
              limit 10
            """
        )
        return Response.json(
            list(
                map(
                    lambda row: {
                        "id": row["id"],
                        "transcript_id": row["transcript_id"],
                        "url": row["url"],
                        "status": row["status"],
                        "submitted_at": row["submitted_at"],
                        "completed_at": row["completed_at"],
                    },
                    result,
                )
            )
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
        (r"^/-/datasette-scribe/api/submit$", Routes.api_submit),
        (r"^/-/datasette-scribe/api/jobs/(?P<database>.*)$", Routes.api_jobs),
    ]
