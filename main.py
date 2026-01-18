import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Column, Integer, String, Text, create_engine, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# 1. 데이터베이스 및 엔진 설정
SQLALCHEMY_DATABASE_URL = "sqlite:///./adhdiary.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. 데이터베이스 모델 (테이블) 정의
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)

class BookRecord(Base):
    __tablename__ = "book_records"
    id = Column(Integer, primary_key=True); title = Column(String); date = Column(String); memo = Column(Text); owner_id = Column(Integer)

class DietRecord(Base):
    __tablename__ = "diet_records"
    id = Column(Integer, primary_key=True); weight = Column(String); meal = Column(String); memo = Column(Text); date = Column(String); owner_id = Column(Integer)

class DailyRecord(Base):
    __tablename__ = "daily_records"
    id = Column(Integer, primary_key=True); emoji = Column(String); memo = Column(Text); date = Column(String); owner_id = Column(Integer)

class FoodRecord(Base):
    __tablename__ = "food_records"
    id = Column(Integer, primary_key=True); place = Column(String); rating = Column(String); memo = Column(Text); date = Column(String); owner_id = Column(Integer)

Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 3. 의존성 및 인증 함수
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def get_current_user(request: Request):
    uid = request.cookies.get("user_id")
    return int(uid) if uid else None

# 4. [기능] 로그인 및 회원가입
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.password == password).first()
    if user:
        res = RedirectResponse(url="/", status_code=303)
        res.set_cookie(key="user_id", value=str(user.id), httponly=True)
        return res
    return RedirectResponse(url="/login", status_code=303)

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
async def signup(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    new_user = User(username=username, password=password)
    db.add(new_user); db.commit()
    return RedirectResponse(url="/login", status_code=303)

# 5. [기능] 메인 페이지 (모든 기록 통합 피드)
@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request, db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    if user_id is None: return RedirectResponse(url="/login")
    
    # 4개 테이블 데이터 모두 가져오기
    b_recs = db.query(BookRecord).filter(BookRecord.owner_id == user_id).all()
    d_recs = db.query(DietRecord).filter(DietRecord.owner_id == user_id).all()
    dy_recs = db.query(DailyRecord).filter(DailyRecord.owner_id == user_id).all()
    f_recs = db.query(FoodRecord).filter(FoodRecord.owner_id == user_id).all()
    
    # 데이터를 메인 피드용 공통 형식으로 변환
    combined = []
    for r in b_recs: combined.append({"id": r.id, "type": "book", "title": f"📖 독서: {r.title}", "date": r.date})
    for r in d_recs: combined.append({"id": r.id, "type": "diet", "title": f"⚖️ 체중: {r.weight}kg 기록", "date": r.date})
    for r in dy_recs: combined.append({"id": r.id, "type": "daily", "title": f"{r.emoji} 일상 기록", "date": r.date})
    for r in f_recs: combined.append({"id": r.id, "type": "food", "title": f"🍴 맛집: {r.place}", "date": r.date})
    
    # 최신순 정렬
    combined.sort(key=lambda x: x['date'], reverse=True)
    
    return templates.TemplateResponse("index.html", {"request": request, "records": combined})

# 6. [기능] 카테고리별 데이터 저장
@app.post("/save_book")
async def s_b(title:str=Form(...), date:str=Form(...), memo:str=Form(...), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    db.add(BookRecord(title=title, date=date, memo=memo, owner_id=uid)); db.commit(); return RedirectResponse("/book", 303)

@app.post("/save_diet")
async def s_d(weight:str=Form(...), meal:str=Form(...), memo:str=Form(...), date:str=Form(...), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    db.add(DietRecord(weight=weight, meal=meal, memo=memo, date=date, owner_id=uid)); db.commit(); return RedirectResponse("/diet", 303)

@app.post("/save_daily")
async def s_dy(emoji:str=Form(...), memo:str=Form(...), date:str=Form(...), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    db.add(DailyRecord(emoji=emoji, memo=memo, date=date, owner_id=uid)); db.commit(); return RedirectResponse("/daily", 303)

@app.post("/save_food")
async def s_f(place:str=Form(...), rating:str=Form(...), memo:str=Form(...), date:str=Form(...), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    db.add(FoodRecord(place=place, rating=rating, memo=memo, date=date, owner_id=uid)); db.commit(); return RedirectResponse("/food", 303)

# 7. [기능] 통합 삭제 시스템
@app.post("/delete_{type}/{record_id}")
async def delete_rec(type:str, record_id:int, db:Session=Depends(get_db), uid=Depends(get_current_user)):
    models = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}
    target = db.query(models[type]).filter(models[type].id == record_id, models[type].owner_id == uid).first()
    if target: 
        db.delete(target)
        db.commit()
    # 현재 보던 카테고리 페이지로 리다이렉트
    return RedirectResponse(f"/{type}", 303)

# 8. [기능] 각 상세 페이지 렌더링
@app.get("/{category}", response_class=HTMLResponse)
async def pages(category:str, request:Request, db:Session=Depends(get_db), uid=Depends(get_current_user)):
    if category in ["favicon.ico", "static"]: return HTMLResponse("")
    if not uid: return RedirectResponse("/login")
    
    models = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}
    if category in models:
        recs = db.query(models[category]).filter(models[category].owner_id == uid).order_by(desc(models[category].id)).all()
        return templates.TemplateResponse(f"{category}.html", {"request": request, "my_records": recs})
    return RedirectResponse("/")
