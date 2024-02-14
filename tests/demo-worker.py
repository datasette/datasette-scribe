from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from time import time
# curl -d '{"id": "a", "url": "https://a.com"}' localhost:5000/submit


async def submit(request):
    data = await request.json()
    job_id = data.get("id")
    url = data.get("url")

    if job_id in app.state.jobs:
        return JSONResponse("no good", status_code=400)

    app.state.jobs[job_id] = {
        "status": "pending",
        "url": url,
        "finish_at": time() + 5,
    }

    return JSONResponse({"status": "pending", "job_id": job_id})


async def status(request):
    job_id = request.path_params["job_id"]
    job = app.state.jobs.get(job_id)
    if job is None:
        return JSONResponse({}, status_code=404)
    if job.get("status") == "pending":
        if job.get("finish_at") < time():
            app.state.jobs[job_id] = {
                "status": "completed",
                "transcript": [
                    {"speaker": "SPEAKER_01", "timestamp": [0.0, 1.2], "text": "aaa"},
                    {"speaker": "SPEAKER_01", "timestamp": [1.2, 3.9], "text": "ccc"},
                    {"speaker": "SPEAKER_02", "timestamp": [3.9, 5.0], "text": "bbb"},
                ],
            }
            return JSONResponse(
                {
                    "completed": True,
                    "error": False,
                    "transcript": app.state.jobs[job_id].get("transcript"),
                }
            )
        return JSONResponse({"completed": False, "error": False, "stage": "TODO"})
    if job.get("status") == "completed":
        return JSONResponse(
            {"completed": True, "error": False, "transcript": job.get("transcript")}
        )
    return JSONResponse({"completed": False, "error": True, "message": "TODO"})


app = Starlette(
    debug=True,
    routes=[
        Route("/submit", submit, methods=["POST"]),
        Route("/status/{job_id}", status),
    ],
)

app.state.jobs = {}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5000, log_level="info")
