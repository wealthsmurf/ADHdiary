import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Column, Integer, String, Text, create_engine, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# 1. DB 설정
SQLALCHEMY_DATABASE_URL = "sqlite:///./adhdiary.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. 모델 정의
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

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def get_current_user(request: Request):
    uid = request.cookies.get("user_id")
    return int(uid) if uid else None

# 3. 로그인 및 회원가입 (아이디 중복 확인 포함)
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.password == password).first()
    if user:
        res = RedirectResponse(url="/", status_code=303)
        res.set_cookie(key="user_id", value=str(user.id), httponly=True)
        return res
    return RedirectResponse(url="/login?error=invalid", status_code=303)

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, error: str = None):
    return templates.TemplateResponse("signup.html", {"request": request, "error": error})

@app.post("/signup")
async def signup(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    # [중복 확인 로직]
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return RedirectResponse(url="/signup?error=exists", status_code=303)
    
    new_user = User(username=username, password=password)
    db.add(new_user); db.commit()
    return RedirectResponse(url="/login?error=registered", status_code=303)

# 4. 메인 피드
@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request, db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    if user_id is None: return RedirectResponse(url="/login")
    
    b = db.query(BookRecord).filter(BookRecord.owner_id == user_id).all()
    d = db.query(DietRecord).filter(DietRecord.owner_id == user_id).all()
    dy = db.query(DailyRecord).filter(DailyRecord.owner_id == user_id).all()
    f = db.query(FoodRecord).filter(FoodRecord.owner_id == user_id).all()
    
    recs = []
    for r in b: recs.append({"id": r.id, "type": "book", "title": f"📖 {r.title}", "date": r.date})
    for r in d: recs.append({"id": r.id, "type": "diet", "title": f"⚖️ {r.weight}kg 기록", "date": r.date})
    for r in dy: recs.append({"id": r.id, "type": "daily", "title": f"{r.emoji} 일상 기록", "date": r.date})
    for r in f: recs.append({"id": r.id, "type": "food", "title": f"🍴 {r.place}", "date": r.date})
    
    recs.sort(key=lambda x: x['date'] if x['date'] else "", reverse=True)
    return templates.TemplateResponse("index.html", {"request": request, "records": recs})

# 5. 모달 상세 데이터 (JS fetch 대응)
@app.get("/{type}/{record_id}")
async def get_detail(type: str, record_id: int, db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    models = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}
    r = db.query(models[type]).filter(models[type].id == record_id, models[type].owner_id == user_id).first()
    if not r: raise HTTPException(status_code=404)
    
    data = {"date": r.date, "memo": r.memo if r.memo else "메모가 없습니다."}
    if type == "book": data["title"] = f"📖 {r.title}"
    elif type == "diet": data["title"] = f"⚖️ {r.weight}kg 기록"
    elif type == "daily": data["title"] = f"{r.emoji} 일상"
    elif type == "food": data["title"] = f"🍴 {r.place}"
    return JSONResponse(data)

# 6. 저장 및 삭제
@app.post("/save_book")
async def save_book(title:str=Form(...), date:str=Form(...), memo:str=Form(...), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    db.add(BookRecord(title=title, date=date, memo=memo, owner_id=uid)); db.commit(); return RedirectResponse("/book", 303)

@app.post("/save_diet")
async def save_diet(weight:str=Form(...), meal:str=Form(...), memo:str=Form(...), date:str=Form(...), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    db.add(DietRecord(weight=weight, meal=meal, memo=memo, date=date, owner_id=uid)); db.commit(); return RedirectResponse("/diet", 303)

@app.post("/save_daily")
async def save_daily(emoji:str=Form(...), memo:str=Form(...), date:str=Form(...), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    db.add(DailyRecord(emoji=emoji, memo=memo, date=date, owner_id=uid)); db.commit(); return RedirectResponse("/daily", 303)

@app.post("/save_food")
async def save_food(place:str=Form(...), rating:str=Form(...), memo:str=Form(...), date:str=Form(...), uid=Depends(get_current_user), db:Session=Depends(get_db)):
    db.add(FoodRecord(place=place, rating=rating, memo=memo, date=date, owner_id=uid)); db.commit(); return RedirectResponse("/food", 303)

@app.post("/delete_{type}/{record_id}")
async def delete_rec(type: str, record_id: int, db: Session = Depends(get_db), uid=Depends(get_current_user)):
    models = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}
    target = db.query(models[type]).filter(models[type].id == record_id, models[type].owner_id == uid).first()
    if target: db.delete(target); db.commit()
    return RedirectResponse("/", 303)

@app.get("/{category}", response_class=HTMLResponse)
async def category_view(category: str, request: Request, db: Session = Depends(get_db), uid=Depends(get_current_user)):
    if category in ["favicon.ico", "static"]: return HTMLResponse("")
    if not uid: return RedirectResponse("/login")
    models = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}
    if category in models:
        recs = db.query(models[category]).filter(models[category].owner_id == uid).order_by(desc(models[category].id)).all()
        return templates.TemplateResponse(f"{category}.html", {"request": request, "my_records": recs})
    return RedirectResponse("/")
