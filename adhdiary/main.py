import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Column, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 1. DB 경로 설정 (Railway Volume 대응)
# Railway 설정에서 Mount Path를 /data로 지정해야 합니다.
if os.path.exists("/data"):
    # 배포 환경 (영구 보존 볼륨 사용)
    SQLALCHEMY_DATABASE_URL = "sqlite:////data/adhdiary.db"
else:
    # 로컬 개발 환경
    SQLALCHEMY_DATABASE_URL = "sqlite:///./adhdiary.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. DB 모델 정의 (4개 카테고리)
class BookRecord(Base):
    __tablename__ = "book_records"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String); date = Column(String); memo = Column(Text)

class DietRecord(Base):
    __tablename__ = "diet_records"
    id = Column(Integer, primary_key=True, index=True)
    weight = Column(String); meal = Column(String); memo = Column(Text); date = Column(String)

class DailyRecord(Base):
    __tablename__ = "daily_records"
    id = Column(Integer, primary_key=True, index=True)
    emoji = Column(String); memo = Column(Text); date = Column(String)

class FoodRecord(Base):
    __tablename__ = "food_records"
    id = Column(Integer, primary_key=True, index=True)
    place = Column(String); rating = Column(String); memo = Column(Text); date = Column(String)

# 테이블 생성
Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 3. API 라우트
@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request):
    db = SessionLocal()
    books = db.query(BookRecord).all()
    diets = db.query(DietRecord).all()
    dailies = db.query(DailyRecord).all()
    foods = db.query(FoodRecord).all()
    
    all_records = []
    for b in books: all_records.append({"id": b.id, "title": f"📖 {b.title}", "date": b.date, "type": "book"})
    for d in diets: all_records.append({"id": d.id, "title": f"⚖️ {d.weight}kg - {d.meal}", "date": d.date, "type": "diet"})
    for dy in dailies: all_records.append({"id": dy.id, "title": f"{dy.emoji} 오늘의 일상", "date": dy.date, "type": "daily"})
    for f in foods: all_records.append({"id": f.id, "title": f"🍴 {f.place} ({f.rating})", "date": f.date, "type": "food"})
    
    all_records.sort(key=lambda x: x['date'], reverse=True)
    db.close()
    return templates.TemplateResponse("index.html", {"request": request, "records": all_records})

# --- 저장 API 모음 ---
@app.post("/save_book")
async def save_book(title: str = Form(...), date: str = Form(...), memo: str = Form(...)):
    db = SessionLocal(); db.add(BookRecord(title=title, date=date, memo=memo)); db.commit(); db.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/save_diet")
async def save_diet(weight: str = Form(...), meal: str = Form(...), memo: str = Form(...), date: str = Form(...)):
    db = SessionLocal(); db.add(DietRecord(weight=weight, meal=meal, memo=memo, date=date)); db.commit(); db.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/save_daily")
async def save_daily(emoji: str = Form(...), memo: str = Form(...), date: str = Form(...)):
    db = SessionLocal(); db.add(DailyRecord(emoji=emoji, memo=memo, date=date)); db.commit(); db.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/save_food")
async def save_food(place: str = Form(...), rating: str = Form(...), memo: str = Form(...), date: str = Form(...)):
    db = SessionLocal(); db.add(FoodRecord(place=place, rating=rating, memo=memo, date=date)); db.commit(); db.close()
    return RedirectResponse(url="/", status_code=303)

# --- 개별 조회 API (JSON 반환) ---
@app.get("/{type}/{record_id}")
async def get_record(type: str, record_id: int):
    db = SessionLocal()
    if type == "book": r = db.query(BookRecord).filter(BookRecord.id == record_id).first()
    elif type == "diet": r = db.query(DietRecord).filter(DietRecord.id == record_id).first()
    elif type == "daily": r = db.query(DailyRecord).filter(DailyRecord.id == record_id).first()
    elif type == "food": r = db.query(FoodRecord).filter(FoodRecord.id == record_id).first()
    
    title = f"📖 {r.title}" if type == "book" else f"⚖️ {r.weight}kg" if type == "diet" else f"{r.emoji} 일상" if type == "daily" else f"🍴 {r.place}"
    result = {"title": title, "date": r.date, "memo": r.memo}
    db.close()
    return result

# --- 삭제 API ---
@app.post("/delete_{type}/{record_id}")
async def delete_record(type: str, record_id: int):
    db = SessionLocal()
    model = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}[type]
    r = db.query(model).filter(model.id == record_id).first()
    if r: db.delete(r); db.commit()
    db.close()
    return RedirectResponse(url="/", status_code=303)
# --- 각 입력 페이지를 보여주는 GET 라우트 (이 부분이 있어야 버튼이 작동합니다) ---

@app.get("/book", response_class=HTMLResponse)
async def book_page(request: Request):
    return templates.TemplateResponse("book.html", {"request": request})

@app.get("/diet", response_class=HTMLResponse)
async def diet_page(request: Request):
    return templates.TemplateResponse("diet.html", {"request": request})

@app.get("/daily", response_class=HTMLResponse)
async def daily_page(request: Request):
    return templates.TemplateResponse("daily.html", {"request": request})

@app.get("/food", response_class=HTMLResponse)
async def food_page(request: Request):
    return templates.TemplateResponse("food.html", {"request": request})