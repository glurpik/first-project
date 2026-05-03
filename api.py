from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
import tempfile
import os
from parser import scrape, save_json, save_xlsx

app = FastAPI(title="Kleinanzeigen Parser API", version="1.0")


@app.get("/search")
def search(
    q: str = Query(..., description="Поисковый запрос"),
    category: str = Query("", description="Категория (необязательно)"),
    pages: int = Query(1, ge=1, le=10, description="Кол-во страниц"),
):
    items = scrape(q, category=category, max_pages=pages)
    return {"query": q, "total": len(items), "results": items}


@app.get("/export/json")
def export_json(
    q: str = Query(...),
    category: str = Query(""),
    pages: int = Query(1, ge=1, le=10),
):
    items = scrape(q, category=category, max_pages=pages)
    path = tempfile.mktemp(suffix=".json")
    save_json(items, path)
    return FileResponse(path, media_type="application/json", filename="results.json")


@app.get("/export/xlsx")
def export_xlsx(
    q: str = Query(...),
    category: str = Query(""),
    pages: int = Query(1, ge=1, le=10),
):
    items = scrape(q, category=category, max_pages=pages)
    path = tempfile.mktemp(suffix=".xlsx")
    save_xlsx(items, path)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="results.xlsx",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
