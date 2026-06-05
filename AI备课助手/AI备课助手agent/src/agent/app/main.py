import asyncio
from fastapi import FastAPI, HTTPException
from app.handlers.task_handlers import handle_task
from app.models.schemas import AcceptedResponse, TaskRequest

app = FastAPI(title='AI Course Agent Python', version='1.0.0')

@app.get('/healthz')
def healthz():
    return {'ok': True}

@app.post('/agent-api/v1/tasks', response_model=AcceptedResponse)
async def create_task(task: TaskRequest):
    try:
        asyncio.create_task(handle_task(task.model_dump()))
        return AcceptedResponse(data={'externalTaskId': task.externalTaskId, 'status': 'accepted'})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
