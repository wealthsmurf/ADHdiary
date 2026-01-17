import os
from fastapi import FastAPI, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Column, Integer, String, Text, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

# 1. DB 설정 (Railway Volume 대응)
if os.path.exists("/data"):
    SQLALCHEMY_DATABASE_URL = "sqlite:////data/adhdiary.db"
else:
    SQLALCHEMY_DATABASE_URL = "sqlite:///./adhdiary.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. DB 모델 정의
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String) # 실제 서비스 시에는 암호화 권장

class BookRecord(Base):
    __tablename__ = "book_records"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String); date = Column(String); memo = Column(Text)
    owner_id = Column(Integer) # 작성자 식별자

class DietRecord(Base):
    __tablename__ = "diet_records"
    id = Column(Integer, primary_key=True, index=True)
    weight = Column(String); meal = Column(String); memo = Column(Text); date = Column(String)
    owner_id = Column(Integer)

class DailyRecord(Base):
    __tablename__ = "daily_records"
    id = Column(Integer, primary_key=True, index=True)
    emoji = Column(String); memo = Column(Text); date = Column(String)
    owner_id = Column(Integer)

class FoodRecord(Base):
    __tablename__ = "food_records"
    id = Column(Integer, primary_key=True, index=True)
    place = Column(String); rating = Column(String); memo = Column(Text); date = Column(String)
    owner_id = Column(Integer)

Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# DB 세션 의존성
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# 로그인 여부 확인 함수
def get_current_user(request: Request):
    return request.cookies.get("user_id")

# 3. 인증 라우트 (회원가입/로그인)
@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
async def signup(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    new_user = User(username=username, password=password)
    db.add(new_user); db.commit()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.password == password).first()
    if user:
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="user_id", value=str(user.id), httponly=True)
        return response
    return RedirectResponse(url="/login?error=true", status_code=303)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("user_id")
    return response

# 4. 메인 페이지 (본인 기록만 조회)
@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request, db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    if not user_id: return RedirectResponse(url="/login")
    
    books = db.query(BookRecord).filter(BookRecord.owner_id == user_id).all()
    diets = db.query(DietRecord).filter(DietRecord.owner_id == user_id).all()
    dailies = db.query(DailyRecord).filter(DailyRecord.owner_id == user_id).all()
    foods = db.query(FoodRecord).filter(FoodRecord.owner_id == user_id).all()
    
    all_records = []
    for b in books: all_records.append({"id": b.id, "title": f"📖 {b.title}", "date": b.date, "type": "book"})
    for d in diets: all_records.append({"id": d.id, "title": f"⚖️ {d.weight}kg - {d.meal}", "date": d.date, "type": "diet"})
    for dy in dailies: all_records.append({"id": dy.id, "title": f"{dy.emoji} 오늘의 일상", "date": dy.date, "type": "daily"})
    for f in foods: all_records.append({"id": f.id, "title": f"🍴 {f.place} ({f.rating})", "date": f.date, "type": "food"})
    
    all_records.sort(key=lambda x: x['date'], reverse=True)
    return templates.TemplateResponse("index.html", {"request": request, "records": all_records})

# --- 저장 API (owner_id 포함) ---
@app.post("/save_book")
async def save_book(title: str = Form(...), date: str = Form(...), memo: str = Form(...), db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    db.add(BookRecord(title=title, date=date, memo=memo, owner_id=user_id)); db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.post("/save_diet")
async def save_diet(weight: str = Form(...), meal: str = Form(...), memo: str = Form(...), date: str = Form(...), db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    db.add(DietRecord(weight=weight, meal=meal, memo=memo, date=date, owner_id=user_id)); db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.post("/save_daily")
async def save_daily(emoji: str = Form(...), memo: str = Form(...), date: str = Form(...), db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    db.add(DailyRecord(emoji=emoji, memo=memo, date=date, owner_id=user_id)); db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.post("/save_food")
async def save_food(place: str = Form(...), rating: str = Form(...), memo: str = Form(...), date: str = Form(...), db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    db.add(FoodRecord(place=place, rating=rating, memo=memo, date=date, owner_id=user_id)); db.commit()
    return RedirectResponse(url="/", status_code=303)

# --- 조회, 삭제, 페이지 라우트는 기존 로직에 user_id 체크 추가하여 유지 ---
@app.get("/{type}/{record_id}")
async def get_record(type: str, record_id: int, db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    model = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}[type]
    r = db.query(model).filter(model.id == record_id, model.owner_id == user_id).first()
    title = f"📖 {r.title}" if type == "book" else f"⚖️ {r.weight}kg" if type == "diet" else f"{r.emoji} 일상" if type == "daily" else f"🍴 {r.place}"
    return {"title": title, "date": r.date, "memo": r.memo}

@app.post("/delete_{type}/{record_id}")
async def delete_record(type: str, record_id: int, db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    model = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}[type]
    r = db.query(model).filter(model.id == record_id, model.owner_id == user_id).first()
    if r: db.delete(r); db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/book", response_class=HTMLResponse)
async def book_page(request: Request, user_id=Depends(get_current_user)):
    if not user_id: return RedirectResponse(url="/login")
    return templates.TemplateResponse("book.html", {"request": request})

@app.get("/diet", response_class=HTMLResponse)
async def diet_page(request: Request, user_id=Depends(get_current_user)):
    if not user_id: return RedirectResponse(url="/login")
    return templates.TemplateResponse("diet.html", {"request": request})

@app.get("/daily", response_class=HTMLResponse)
async def daily_page(request: Request, user_id=Depends(get_current_user)):
    if not user_id: return RedirectResponse(url="/login")
    return templates.TemplateResponse("daily.html", {"request": request})

@app.get("/food", response_class=HTMLResponse)
async def food_page(request: Request, user_id=Depends(get_current_user)):
    if not user_id: return RedirectResponse(url="/login")
    return templates.TemplateResponse("food.html", {"request": request})