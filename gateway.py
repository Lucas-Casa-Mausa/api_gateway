from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="API Gateway", redoc_url=None, docs_url=None, version="1.0.0")

SERVICES = {
    "users": "http://localhost:8001",
    "orders": "http://localhost:8002",
    "products": "http://localhost:8003"
}

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Status: {response.status_code}")
    return response

@app.get("/")
async def root():
    return {
        "message": "Welcome to the API Gateway",
        "services": list(SERVICES.keys())
    }

@app.get("/health")
async def health_check():
    health_status = {"gateway": "healthy", "services": {}}

    async with httpx.AsyncClient(timeout=5.0) as client:
        for service_name, service_url in SERVICES.items():
            try:
                response = await client.get(f"{service_url}/health")
                health_status["services"][service_name] = "healthy"
            except Exception as e:
                health_status["services"][service_name] = "unhealthy"
                logger.error(f"Service {service_name} is not alive: {e}")

    return health_status

@app.api_route("/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def gateway_proxy(service: str, path: str, request: Request):
    if service not in SERVICES:
        raise HTTPException(status_code=404, detail="Service not found")

    service_url = SERVICES[service]
    target_url = f"{service_url}/{path}"

    if request.url.query:
        target_url += f"?{request.url.query}"

    logger.info(f"Redirecting to: {target_url}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            body = await request.body()

            response = client.request(
                method=request.method,
                url=target_url,
                headers={k: v for k, v in request.headers.items()
                        if k.lower() not in ["host", "connection"]},
                content=body
            )

            return JSONResponse(
                content=response.json() if response.text else {},
                status_code=response.status_code,
                headers=dict(response.headers)
            )
    except httpx.TimeoutException:
        logger.error("Request to service timed out")
        raise HTTPException(status_code=504, detail="Gateway Timeout")

    except httpx.ConnectError:
        logger.error("Failed to connect to service")
        raise HTTPException(status_code=503, detail="Service Unavailable")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail="Internal Gateway Error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)