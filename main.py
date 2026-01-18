import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Column, Integer, String, Text, create_engine, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# 1. DB 설정 (Railway 등 외부 서버 Volume 대응)
DB_DIR = "/data" if os.path.exists("/data") else "."
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_DIR}/adhdiary.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. DB 모델 정의
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

# 3. 헬퍼 함수 (DB 및 유저 인증)
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def get_current_user(request: Request):
    uid = request.cookies.get("user_id")
    return int(uid) if uid else None

# 4. 인증 라우트 (로그인/회원가입/로그아웃)
@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_post(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.password == password).first()
    if user:
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="user_id", value=str(user.id), httponly=True, max_age=31536000, samesite="lax")
        return response
    return RedirectResponse(url="/login?error=true", status_code=303)

@app.get("/signup", response_class=HTMLResponse)
async def signup_get(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
async def signup_post(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == username).first():
        return RedirectResponse(url="/signup?error=exists", status_code=303)
    db.add(User(username=username, password=password)); db.commit()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/logout")
async def logout():
    res = RedirectResponse(url="/login"); res.delete_cookie("user_id"); return res

# 5. 메인 페이지 (전체 피드)
@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request, db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    if user_id is None: return RedirectResponse(url="/login")
    
    books = db.query(BookRecord).filter(BookRecord.owner_id == user_id).all()
    diets = db.query(DietRecord).filter(DietRecord.owner_id == user_id).all()
    dailies = db.query(DailyRecord).filter(DailyRecord.owner_id == user_id).all()
    foods = db.query(FoodRecord).filter(FoodRecord.owner_id == user_id).all()
    
    all_records = []
    for b in books: all_records.append({"id": b.id, "title": f"📖 {b.title}", "date": b.date, "type": "book"})
    for d in diets: all_records.append({"id": d.id, "title": f"⚖️ {d.weight}kg", "date": d.date, "type": "diet"})
    for dy in dailies: all_records.append({"id": dy.id, "title": f"{dy.emoji} 일상", "date": dy.date, "type": "daily"})
    for f in foods: all_records.append({"id": f.id, "title": f"🍴 {f.place}", "date": f.date, "type": "food"})
    
    all_records.sort(key=lambda x: x['date'], reverse=True)
    return templates.TemplateResponse("index.html", {"request": request, "records": all_records})

# 6. 저장 및 삭제 API (카테고리 리턴)
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

@app.post("/delete_{type}/{record_id}")
async def delete_record(type: str, record_id: int, db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    model_map = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}
    model = model_map.get(type)
    r = db.query(model).filter(model.id == record_id, model.owner_id == user_id).first()
    if r: db.delete(r); db.commit()
    return RedirectResponse(f"/{type}", 303)

# 7. 카테고리별 페이지 (과거 기록 포함)
@app.get("/{category_name}", response_class=HTMLResponse)
async def category_pages(category_name: str, request: Request, db: Session = Depends(get_db), user_id=Depends(get_current_user)):
    # 특수 경로 예외 처리 (로그인/회원가입은 이미 위에서 처리됨)
    if category_name in ["favicon.ico", "static"]: return HTMLResponse("")
    if not user_id: return RedirectResponse(url="/login")

    model_map = {"book": BookRecord, "diet": DietRecord, "daily": DailyRecord, "food": FoodRecord}
    
    if category_name in model_map:
        model = model_map[category_name]
        my_records = db.query(model).filter(model.owner_id == user_id).order_by(desc(model.id)).all()
        return templates.TemplateResponse(f"{category_name}.html", {"request": request, "my_records": my_records})
    
    return RedirectResponse(url="/")
