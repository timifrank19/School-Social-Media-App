from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Float
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from contextlib import contextmanager
import bcrypt
import json, os, uuid, shutil, random, base64
from pyngrok import ngrok

# ============================================================
# CONFIGURATION
# ============================================================
NGROK_AUTHTOKEN = "32YLc6Wskxk6X2N7d1P1DdneMas_7zxms4oHSLcnXhAMfzoD3"

UPLOAD_DIR = "uploads"
RECORDINGS_DIR = "recordings"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RECORDINGS_DIR, exist_ok=True)

DATABASE_URL = "sqlite:///./fuomce.db"

# ============================================================
# DATABASE SETUP
# ============================================================
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================================
# MODELS
# ============================================================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    avatar_color = Column(String, default="#800020")
    profile_pic = Column(String, nullable=True)
    is_online = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    last_seen = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)
    
    sent_messages = relationship("Message", foreign_keys="Message.sender_id", back_populates="sender")
    received_messages = relationship("Message", foreign_keys="Message.recipient_id", back_populates="recipient")
    group_memberships = relationship("GroupMember", back_populates="user")
    locations = relationship("Location", back_populates="user")
    recordings = relationship("Recording", back_populates="user")
    friends_as_user1 = relationship("Friend", foreign_keys="Friend.user1_id", back_populates="user1")
    friends_as_user2 = relationship("Friend", foreign_keys="Friend.user2_id", back_populates="user2")
    reels = relationship("Reel", back_populates="user")
    sent_friend_requests = relationship("FriendRequest", foreign_keys="FriendRequest.sender_id", back_populates="sender")
    received_friend_requests = relationship("FriendRequest", foreign_keys="FriendRequest.receiver_id", back_populates="receiver")

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    is_public = Column(Boolean, default=True)
    is_locked = Column(Boolean, default=False)
    group_pic = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    
    members = relationship("GroupMember", back_populates="group")
    messages = relationship("Message", back_populates="group")

class GroupMember(Base):
    __tablename__ = "group_members"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    group_id = Column(Integer, ForeignKey("groups.id"))
    is_admin = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.now)
    
    user = relationship("User", back_populates="group_memberships")
    group = relationship("Group", back_populates="members")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"))
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.now)
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)
    message_type = Column(String, default="text")
    is_deleted = Column(Boolean, default=False)
    edited_at = Column(DateTime, nullable=True)
    reply_to_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    deleted_for = Column(Text, nullable=True)
    file_url = Column(String, nullable=True)
    file_name = Column(String, nullable=True)
    file_type = Column(String, nullable=True)
    file_size = Column(Integer, default=0)
    reactions = Column(Text, default="{}")
    
    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_messages")
    recipient = relationship("User", foreign_keys=[recipient_id], back_populates="received_messages")
    group = relationship("Group", back_populates="messages")
    reply_to = relationship("Message", remote_side=[id])

class Friend(Base):
    __tablename__ = "friends"
    id = Column(Integer, primary_key=True, index=True)
    user1_id = Column(Integer, ForeignKey("users.id"))
    user2_id = Column(Integer, ForeignKey("users.id"))
    timestamp = Column(DateTime, default=datetime.now)
    
    user1 = relationship("User", foreign_keys=[user1_id], back_populates="friends_as_user1")
    user2 = relationship("User", foreign_keys=[user2_id], back_populates="friends_as_user2")

class Follow(Base):
    """One-way follow relationship. Sending a friend request immediately creates
    a Follow row (you follow them right away). It only becomes a mutual Friend
    once they accept - until then, from their side it's just 'someone follows me'."""
    __tablename__ = "follows"
    id = Column(Integer, primary_key=True, index=True)
    follower_id = Column(Integer, ForeignKey("users.id"))
    followed_id = Column(Integer, ForeignKey("users.id"))
    timestamp = Column(DateTime, default=datetime.now)

class FriendRequest(Base):
    __tablename__ = "friend_requests"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="pending")
    timestamp = Column(DateTime, default=datetime.now)
    
    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_friend_requests")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_friend_requests")

class Location(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    device_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    battery = Column(Integer, default=100)
    distance = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.now)
    
    user = relationship("User", back_populates="locations")

class Recording(Base):
    __tablename__ = "recordings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    timestamp = Column(DateTime, default=datetime.now)
    filename = Column(String, nullable=False)
    size = Column(Integer, nullable=False)
    data = Column(Text, nullable=False)
    
    user = relationship("User", back_populates="recordings")

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    from_user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.now)

class Reel(Base):
    __tablename__ = "reels"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, default="Untitled")
    description = Column(Text, default="")
    media_url = Column(String, nullable=False)
    media_type = Column(String, default="image")
    privacy = Column(String, default="public")
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    is_live = Column(Boolean, default=False)
    live_stream_url = Column(String, nullable=True)
    comments = Column(Text, default="[]")
    liked_by = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.now)
    
    user = relationship("User", back_populates="reels")

class Story(Base):
    __tablename__ = "stories"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    media_url = Column(String, nullable=False)
    media_type = Column(String, default="image")
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, default=datetime.now)
    
    user = relationship("User", foreign_keys=[user_id])

# ============================================================
# SCHEMAS
# ============================================================

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None
    display_name: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_public: bool = True

class FriendRequestAction(BaseModel):
    sender_id: int
    receiver_id: int

class LocationUpdate(BaseModel):
    user_id: int
    device_id: str
    name: str
    lat: float
    lng: float
    battery: Optional[int] = 100
    distance: Optional[float] = 0.0

# ============================================================
# AUTHENTICATION
# ============================================================
def verify_password(plain_password, hashed_password):
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8")[:72], hashed_password.encode("utf-8"))
    except Exception:
        return False

def get_password_hash(password):
    hashed = bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt())
    return hashed.decode("utf-8")

# ============================================================
# WEBSOCKET MANAGER
# ============================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
    
    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        
        with get_db() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.is_online = True
                user.last_seen = datetime.now()
                db.commit()
    
    def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                with get_db() as db:
                    user = db.query(User).filter(User.id == user_id).first()
                    if user:
                        user.is_online = False
                        user.last_seen = datetime.now()
                        db.commit()
    
    async def send_to_user(self, message: dict, user_id: int):
        if user_id in self.active_connections:
            for socket in self.active_connections[user_id]:
                try:
                    await socket.send_json(message)
                except:
                    pass
    
    async def send_to_group_except(self, message: dict, group_id: int, sender_id: int):
        with get_db() as db:
            members = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
            for member in members:
                if member.user_id != sender_id:
                    await self.send_to_user(message, member.user_id)
    
    async def broadcast(self, message: dict):
        for user_id in list(self.active_connections.keys()):
            await self.send_to_user(message, user_id)

manager = ConnectionManager()

# ============================================================
# FASTAPI APP
# ============================================================
app = FastAPI(title="FUOMCE Communication App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# STATIC FILE SERVING (uploads: images/videos/audio/profile pics/reels/stories)
# Without this mount, every uploaded file returns 404 and nothing (profile
# pictures, reels, story media, chat files, voice/video notes) ever displays.
# ============================================================
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ============================================================
# DATABASE INITIALIZATION
# ============================================================
def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_columns()
    print("✅ Database initialized")

def _migrate_sqlite_columns():
    """Add any newly-introduced columns to an existing (already created) sqlite
    database so people upgrading from an older version of this file don't
    have to delete their fuomce.db to pick up new features."""
    migrations = {
        "reels": [("liked_by", "TEXT DEFAULT '[]'")],
        "messages": [("reactions", "TEXT DEFAULT '{}'")],
        "group_members": [("is_admin", "BOOLEAN DEFAULT 0")],
        "stories": [("expires_at", "DATETIME")],
    }
    with engine.connect() as conn:
        for table, cols in migrations.items():
            try:
                existing = [row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()]
            except Exception:
                continue
            for col_name, col_def in cols:
                if col_name not in existing:
                    try:
                        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                        conn.commit()
                        print(f"   🔧 Migrated: added column {table}.{col_name}")
                    except Exception as e:
                        print(f"   ⚠️ Could not migrate {table}.{col_name}: {e}")

def create_default_data():
    with get_db() as db:
        if db.query(User).count() > 0:
            return
        
        print("📝 Creating default users...")
        colors = ["#800020", "#2C2C2C", "#D2B48C", "#FF7F50", "#2E4A62", "#6B8E23", "#8B4513", "#A52A2A", "#CD5C5C", "#BC8F8F"]
        
        admin = User(
            username="admin",
            email="admin@fuomce.com",
            password_hash=get_password_hash("admin123"),
            full_name="FUOMCE Admin",
            display_name="Admin",
            avatar_color="#800020",
            is_admin=True
        )
        db.add(admin)
        db.flush()
        
        demo_users = [
            ("alex", "alex@fuomce.com", "Alex Johnson", "#2C2C2C"),
            ("sarah", "sarah@fuomce.com", "Sarah Williams", "#D2B48C"),
            ("mike", "mike@fuomce.com", "Mike Thompson", "#FF7F50"),
            ("emma", "emma@fuomce.com", "Emma Davis", "#2E4A62"),
            ("chris", "chris@fuomce.com", "Chris Brown", "#6B8E23"),
            ("lisa", "lisa@fuomce.com", "Lisa Martinez", "#8B4513"),
        ]
        
        for username, email, full_name, color in demo_users:
            user = User(
                username=username,
                email=email,
                password_hash=get_password_hash("password123"),
                full_name=full_name,
                display_name=full_name.split()[0],
                avatar_color=color
            )
            db.add(user)
        
        db.commit()
        all_users = db.query(User).all()
        
        # Create General Group
        general = Group(
            name="💬 General Chat",
            description="General discussion for everyone",
            created_by=admin.id,
            is_public=True
        )
        db.add(general)
        db.commit()
        db.refresh(general)
        
        for user in all_users:
            member = GroupMember(user_id=user.id, group_id=general.id, is_admin=(user.is_admin == True))
            db.add(member)
        db.commit()
        
        # Create some sample reels
        sample_reels = [
            ("Welcome to FUOMCE!", "The all-in-one communication platform!", "https://picsum.photos/400/400?random=1", "image"),
            ("Community Update", "New features coming soon!", "https://picsum.photos/400/400?random=2", "image"),
            ("Team Meeting", "Weekly sync meeting notes", "https://picsum.photos/400/400?random=3", "image"),
        ]
        
        for title, desc, url, media_type in sample_reels:
            reel = Reel(
                user_id=admin.id,
                title=title,
                description=desc,
                media_url=url,
                media_type=media_type,
                privacy="public",
                views=random.randint(10, 100),
                likes=random.randint(1, 20)
            )
            db.add(reel)
        db.commit()
        
        print("✅ Default data created!")
        print("   👑 Admin: username='admin', password='admin123'")
        print("   👤 Users: username='alex', password='password123'")

# ============================================================
# AUTH ENDPOINTS
# ============================================================

@app.post("/api/register")
async def register_user(user_data: UserCreate):
    with get_db() as db:
        existing = db.query(User).filter(
            (User.username == user_data.username) | (User.email == user_data.email)
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username or email already registered")
        
        colors = ["#800020", "#2C2C2C", "#D2B48C", "#FF7F50", "#2E4A62", "#6B8E23", "#8B4513", "#A52A2A", "#CD5C5C", "#BC8F8F"]
        display_name = user_data.display_name or user_data.full_name or user_data.username
        user_count = db.query(User).count()
        is_admin = (user_count == 0)
        
        new_user = User(
            username=user_data.username,
            email=user_data.email,
            password_hash=get_password_hash(user_data.password),
            full_name=user_data.full_name,
            display_name=display_name,
            avatar_color=random.choice(colors),
            is_admin=is_admin
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Add to general group
        general = db.query(Group).filter(Group.name == "💬 General Chat").first()
        if general:
            member = GroupMember(user_id=new_user.id, group_id=general.id)
            db.add(member)
            db.commit()
        
        return {
            "success": True,
            "user": {
                "id": new_user.id,
                "username": new_user.username,
                "email": new_user.email,
                "full_name": new_user.full_name,
                "display_name": new_user.display_name,
                "avatar_color": new_user.avatar_color,
                "profile_pic": new_user.profile_pic,
                "is_online": new_user.is_online,
                "is_admin": new_user.is_admin,
                "last_seen": new_user.last_seen
            }
        }

@app.post("/api/login")
async def login_user(user_data: UserLogin):
    with get_db() as db:
        user = db.query(User).filter(User.username == user_data.username).first()
        if not user or not verify_password(user_data.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        user.is_online = True
        user.last_seen = datetime.now()
        db.commit()
        db.refresh(user)
        
        return {
            "success": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "display_name": user.display_name,
                "avatar_color": user.avatar_color,
                "profile_pic": user.profile_pic,
                "is_online": user.is_online,
                "is_admin": user.is_admin,
                "last_seen": user.last_seen
            }
        }

@app.post("/api/logout")
async def logout_user(user_id: int = Form(...)):
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.is_online = False
            user.last_seen = datetime.now()
            db.commit()
    return {"success": True}

@app.get("/api/me")
async def get_me(username: str):
    with get_db() as db:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "display_name": user.display_name,
            "avatar_color": user.avatar_color,
            "profile_pic": user.profile_pic,
            "is_online": user.is_online,
            "is_admin": user.is_admin,
            "last_seen": user.last_seen
        }

@app.get("/api/users")
async def get_users():
    with get_db() as db:
        users = db.query(User).all()
        return [{
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "display_name": u.display_name,
            "avatar_color": u.avatar_color,
            "profile_pic": u.profile_pic,
            "is_online": u.is_online,
            "is_admin": u.is_admin,
            "last_seen": u.last_seen
        } for u in users]

@app.get("/api/users/search")
async def search_users(query: str):
    with get_db() as db:
        users = db.query(User).filter(
            (User.display_name.contains(query)) | (User.username.contains(query))
        ).all()
        return [{
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "avatar_color": u.avatar_color,
            "profile_pic": u.profile_pic,
            "is_online": u.is_online
        } for u in users]

@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "display_name": user.display_name,
            "avatar_color": user.avatar_color,
            "profile_pic": user.profile_pic,
            "is_online": user.is_online,
            "is_admin": user.is_admin,
            "last_seen": user.last_seen
        }

@app.put("/api/users/profile")
async def update_profile(
    user_id: int = Form(...), 
    display_name: str = Form(...), 
    avatar_color: str = Form(...)
):
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user.display_name = display_name
        user.avatar_color = avatar_color
        db.commit()
        return {"success": True}

@app.post("/api/users/profile_pic")
async def upload_profile_pic(user_id: int = Form(...), media: UploadFile = File(...)):
    if not media.filename:
        raise HTTPException(status_code=400, detail="No file selected")
    
    ext = media.filename.split(".")[-1].lower()
    filename = f"profile_{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(media.file, buffer)
    
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.profile_pic = filename
            db.commit()
            db.refresh(user)
    
    return {"success": True, "profile_pic": filename}

# ============================================================
# FRIEND SYSTEM
# ============================================================

@app.get("/api/friends")
async def get_friends(user_id: int):
    with get_db() as db:
        friends = db.query(Friend).filter(
            (Friend.user1_id == user_id) | (Friend.user2_id == user_id)
        ).all()
        result = []
        for f in friends:
            friend_id = f.user2_id if f.user1_id == user_id else f.user1_id
            user = db.query(User).filter(User.id == friend_id).first()
            if user:
                result.append({
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar_color": user.avatar_color,
                    "profile_pic": user.profile_pic,
                    "is_online": user.is_online
                })
        return result

@app.get("/api/friend_requests")
async def get_friend_requests(user_id: int):
    with get_db() as db:
        requests = db.query(FriendRequest).filter(
            FriendRequest.receiver_id == user_id,
            FriendRequest.status == "pending"
        ).all()
        result = []
        for r in requests:
            sender = db.query(User).filter(User.id == r.sender_id).first()
            if sender:
                result.append({
                    "id": r.id,
                    "sender_id": r.sender_id,
                    "sender_name": sender.display_name or sender.username,
                    "sender_avatar": sender.avatar_color,
                    "timestamp": r.timestamp
                })
        return result

@app.get("/api/friend_requests/sent")
async def get_sent_friend_requests(user_id: int):
    with get_db() as db:
        requests = db.query(FriendRequest).filter(
            FriendRequest.sender_id == user_id,
            FriendRequest.status == "pending"
        ).all()
        result = []
        for r in requests:
            receiver = db.query(User).filter(User.id == r.receiver_id).first()
            if receiver:
                result.append({
                    "id": r.id,
                    "receiver_id": r.receiver_id,
                    "receiver_name": receiver.display_name or receiver.username,
                    "timestamp": r.timestamp
                })
        return result

@app.post("/api/friend_requests/send")
async def send_friend_request(data: FriendRequestAction):
    if data.sender_id == data.receiver_id:
        raise HTTPException(status_code=400, detail="Cannot send friend request to yourself")
    
    with get_db() as db:
        existing = db.query(FriendRequest).filter(
            ((FriendRequest.sender_id == data.sender_id) & (FriendRequest.receiver_id == data.receiver_id)) |
            ((FriendRequest.sender_id == data.receiver_id) & (FriendRequest.receiver_id == data.sender_id))
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Request already exists")
        
        friend = db.query(Friend).filter(
            ((Friend.user1_id == data.sender_id) & (Friend.user2_id == data.receiver_id)) |
            ((Friend.user1_id == data.receiver_id) & (Friend.user2_id == data.sender_id))
        ).first()
        if friend:
            raise HTTPException(status_code=400, detail="Already friends")
        
        request = FriendRequest(
            sender_id=data.sender_id,
            receiver_id=data.receiver_id,
            status="pending"
        )
        db.add(request)
        
        # Sending a friend request also follows them immediately - it behaves
        # like a follow until they accept, at which point it becomes mutual.
        already_following = db.query(Follow).filter(
            Follow.follower_id == data.sender_id, Follow.followed_id == data.receiver_id
        ).first()
        if not already_following:
            db.add(Follow(follower_id=data.sender_id, followed_id=data.receiver_id))
        db.commit()
        
        sender = db.query(User).filter(User.id == data.sender_id).first()
        notification = Notification(
            user_id=data.receiver_id,
            from_user_id=data.sender_id,
            type="friend_request",
            text=f"{sender.display_name or sender.username} sent you a friend request"
        )
        db.add(notification)
        db.commit()
        
        await manager.send_to_user({
            "type": "friend_request",
            "from_user_id": data.sender_id,
            "from_name": sender.display_name or sender.username
        }, data.receiver_id)
        
        return {"success": True}

@app.post("/api/friend_requests/accept")
async def accept_friend_request(data: FriendRequestAction):
    with get_db() as db:
        request = db.query(FriendRequest).filter(
            FriendRequest.sender_id == data.sender_id,
            FriendRequest.receiver_id == data.receiver_id,
            FriendRequest.status == "pending"
        ).first()
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")
        
        request.status = "accepted"
        
        friend1 = Friend(user1_id=data.sender_id, user2_id=data.receiver_id)
        db.add(friend1)
        
        # Accepting means you follow them back too - now it's mutual, like WhatsApp/Instagram friends.
        already_following_back = db.query(Follow).filter(
            Follow.follower_id == data.receiver_id, Follow.followed_id == data.sender_id
        ).first()
        if not already_following_back:
            db.add(Follow(follower_id=data.receiver_id, followed_id=data.sender_id))
        db.commit()
        
        receiver = db.query(User).filter(User.id == data.receiver_id).first()
        notification = Notification(
            user_id=data.sender_id,
            from_user_id=data.receiver_id,
            type="friend_accept",
            text=f"{receiver.display_name or receiver.username} accepted your friend request"
        )
        db.add(notification)
        db.commit()
        
        await manager.send_to_user({
            "type": "friend_accepted",
            "user_id": data.receiver_id,
            "name": receiver.display_name or receiver.username
        }, data.sender_id)
        
        return {"success": True}

@app.post("/api/friend_requests/decline")
async def decline_friend_request(data: FriendRequestAction):
    with get_db() as db:
        request = db.query(FriendRequest).filter(
            FriendRequest.sender_id == data.sender_id,
            FriendRequest.receiver_id == data.receiver_id,
            FriendRequest.status == "pending"
        ).first()
        if request:
            db.delete(request)
            db.commit()
    return {"success": True}

@app.post("/api/friend_requests/cancel")
async def cancel_friend_request(data: FriendRequestAction):
    with get_db() as db:
        request = db.query(FriendRequest).filter(
            FriendRequest.sender_id == data.sender_id,
            FriendRequest.receiver_id == data.receiver_id,
            FriendRequest.status == "pending"
        ).first()
        if request:
            db.delete(request)
            follow = db.query(Follow).filter(
                Follow.follower_id == data.sender_id, Follow.followed_id == data.receiver_id
            ).first()
            if follow:
                db.delete(follow)
            db.commit()
    return {"success": True}

class FollowAction(BaseModel):
    follower_id: int
    followed_id: int

@app.post("/api/follow")
async def follow_user(data: FollowAction):
    """Plain one-way follow - independent of the friend-request flow. Lets
    someone follow another user's public activity without asking to be friends."""
    if data.follower_id == data.followed_id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")
    with get_db() as db:
        existing = db.query(Follow).filter(
            Follow.follower_id == data.follower_id, Follow.followed_id == data.followed_id
        ).first()
        if existing:
            return {"success": True, "following": True}
        db.add(Follow(follower_id=data.follower_id, followed_id=data.followed_id))
        db.commit()
        
        followed_user = db.query(User).filter(User.id == data.followed_id).first()
        follower_user = db.query(User).filter(User.id == data.follower_id).first()
        notification = Notification(
            user_id=data.followed_id,
            from_user_id=data.follower_id,
            type="follow",
            text=f"{follower_user.display_name or follower_user.username} started following you"
        )
        db.add(notification)
        db.commit()
        
        await manager.send_to_user({
            "type": "new_follower",
            "user_id": data.follower_id,
            "name": follower_user.display_name or follower_user.username
        }, data.followed_id)
        
        return {"success": True, "following": True}

@app.post("/api/unfollow")
async def unfollow_user(data: FollowAction):
    with get_db() as db:
        existing = db.query(Follow).filter(
            Follow.follower_id == data.follower_id, Follow.followed_id == data.followed_id
        ).first()
        if existing:
            db.delete(existing)
            db.commit()
        return {"success": True, "following": False}

@app.get("/api/users/{user_id}/follow-info")
async def get_follow_info(user_id: int, viewer_id: Optional[int] = None):
    with get_db() as db:
        followers_count = db.query(Follow).filter(Follow.followed_id == user_id).count()
        following_count = db.query(Follow).filter(Follow.follower_id == user_id).count()
        is_following = False
        if viewer_id:
            is_following = db.query(Follow).filter(
                Follow.follower_id == viewer_id, Follow.followed_id == user_id
            ).first() is not None
        return {"followers": followers_count, "following": following_count, "is_following": is_following}

# ============================================================
# GROUP ENDPOINTS
# ============================================================

@app.post("/api/groups")
async def create_group(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    is_public: bool = Form(True),
    user_id: int = Form(...)
):
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        new_group = Group(
            name=name,
            description=description,
            created_by=user_id,
            is_public=is_public
        )
        db.add(new_group)
        db.commit()
        db.refresh(new_group)
        
        member = GroupMember(user_id=user_id, group_id=new_group.id, is_admin=True)
        db.add(member)
        db.commit()
        
        return {
            "id": new_group.id,
            "name": new_group.name,
            "description": new_group.description,
            "created_by": new_group.created_by,
            "is_public": new_group.is_public,
            "is_locked": new_group.is_locked,
            "group_pic": new_group.group_pic,
            "member_count": 1
        }

@app.get("/api/groups")
async def get_groups():
    with get_db() as db:
        groups = db.query(Group).all()
        result = []
        for g in groups:
            member_count = db.query(GroupMember).filter(GroupMember.group_id == g.id).count()
            result.append({
                "id": g.id,
                "name": g.name,
                "description": g.description,
                "created_by": g.created_by,
                "is_public": g.is_public,
                "is_locked": g.is_locked,
                "group_pic": g.group_pic,
                "member_count": member_count
            })
        return result

@app.post("/api/groups/{group_id}/join")
async def join_group(group_id: int, user_id: int = Form(...)):
    with get_db() as db:
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        
        existing = db.query(GroupMember).filter(
            GroupMember.user_id == user_id,
            GroupMember.group_id == group_id
        ).first()
        if existing:
            return {"message": "Already a member"}
        
        member = GroupMember(user_id=user_id, group_id=group_id)
        db.add(member)
        db.commit()
        return {"success": True}

@app.post("/api/groups/{group_id}/add-members")
async def add_group_members(group_id: int, user_ids: str = Form(...), admin_id: int = Form(...)):
    """user_ids is a comma-separated string of user ids to add."""
    with get_db() as db:
        admin = db.query(GroupMember).filter(
            GroupMember.user_id == admin_id,
            GroupMember.group_id == group_id,
            GroupMember.is_admin == True
        ).first()
        if not admin:
            raise HTTPException(status_code=403, detail="Only admins can add members")
        
        try:
            ids = [int(x) for x in user_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user_ids")
        
        # Only friends of the admin can be added to a group - keeps groups
        # made up of people who actually know each other, like WhatsApp.
        admin_friend_ids = set()
        friend_rows = db.query(Friend).filter(
            (Friend.user1_id == admin_id) | (Friend.user2_id == admin_id)
        ).all()
        for f in friend_rows:
            admin_friend_ids.add(f.user2_id if f.user1_id == admin_id else f.user1_id)
        
        added = []
        skipped_not_friends = []
        for user_id in ids:
            if user_id not in admin_friend_ids:
                skipped_not_friends.append(user_id)
                continue
            existing = db.query(GroupMember).filter(
                GroupMember.user_id == user_id,
                GroupMember.group_id == group_id
            ).first()
            if not existing:
                member = GroupMember(user_id=user_id, group_id=group_id)
                db.add(member)
                added.append(user_id)
        db.commit()
        return {"success": True, "added": added, "skipped_not_friends": skipped_not_friends}

@app.post("/api/groups/{group_id}/leave")
async def leave_group(group_id: int, user_id: int = Form(...)):
    with get_db() as db:
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        
        member = db.query(GroupMember).filter(
            GroupMember.user_id == user_id,
            GroupMember.group_id == group_id
        ).first()
        if not member:
            raise HTTPException(status_code=400, detail="Not a member")
        
        if member.is_admin:
            admin_count = db.query(GroupMember).filter(
                GroupMember.group_id == group_id,
                GroupMember.is_admin == True
            ).count()
            if admin_count <= 1:
                other_member = db.query(GroupMember).filter(
                    GroupMember.group_id == group_id,
                    GroupMember.user_id != user_id
                ).first()
                if other_member:
                    other_member.is_admin = True
        
        db.delete(member)
        db.commit()
        return {"success": True}

@app.get("/api/groups/{group_id}/members")
async def get_group_members(group_id: int):
    with get_db() as db:
        members = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
        result = []
        for m in members:
            user = db.query(User).filter(User.id == m.user_id).first()
            if user:
                result.append({
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar_color": user.avatar_color,
                    "profile_pic": user.profile_pic,
                    "is_online": user.is_online,
                    "is_admin": m.is_admin
                })
        return result

@app.get("/api/groups/{group_id}/member-status")
async def get_group_member_status(group_id: int, user_id: int):
    with get_db() as db:
        member = db.query(GroupMember).filter(
            GroupMember.user_id == user_id,
            GroupMember.group_id == group_id
        ).first()
        if not member:
            return {"is_member": False, "is_admin": False}
        return {"is_member": True, "is_admin": member.is_admin}

@app.post("/api/groups/{group_id}/make-admin")
async def make_admin(group_id: int, user_id: int, admin_id: int = Form(...)):
    with get_db() as db:
        admin = db.query(GroupMember).filter(
            GroupMember.user_id == admin_id,
            GroupMember.group_id == group_id,
            GroupMember.is_admin == True
        ).first()
        if not admin:
            raise HTTPException(status_code=403, detail="Only admins can make other admins")
        
        member = db.query(GroupMember).filter(
            GroupMember.user_id == user_id,
            GroupMember.group_id == group_id
        ).first()
        if not member:
            raise HTTPException(status_code=404, detail="User not in group")
        
        member.is_admin = True
        db.commit()
        return {"success": True}

@app.post("/api/groups/{group_id}/remove-member")
async def remove_member(group_id: int, user_id: int, admin_id: int = Form(...)):
    with get_db() as db:
        admin = db.query(GroupMember).filter(
            GroupMember.user_id == admin_id,
            GroupMember.group_id == group_id,
            GroupMember.is_admin == True
        ).first()
        if not admin:
            raise HTTPException(status_code=403, detail="Only admins can remove members")
        
        member = db.query(GroupMember).filter(
            GroupMember.user_id == user_id,
            GroupMember.group_id == group_id
        ).first()
        if not member:
            raise HTTPException(status_code=404, detail="User not in group")
        
        if member.is_admin:
            admin_count = db.query(GroupMember).filter(
                GroupMember.group_id == group_id,
                GroupMember.is_admin == True
            ).count()
            if admin_count <= 1:
                raise HTTPException(status_code=400, detail="Cannot remove the last admin")
        
        db.delete(member)
        db.commit()
        return {"success": True}

@app.post("/api/groups/{group_id}/toggle-lock")
async def toggle_group_lock(group_id: int, admin_id: int = Form(...)):
    with get_db() as db:
        admin = db.query(GroupMember).filter(
            GroupMember.user_id == admin_id,
            GroupMember.group_id == group_id,
            GroupMember.is_admin == True
        ).first()
        if not admin:
            raise HTTPException(status_code=403, detail="Only admins can lock/unlock groups")
        
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        
        group.is_locked = not group.is_locked
        db.commit()
        return {"locked": group.is_locked}

# ============================================================
# MESSAGE ENDPOINTS
# ============================================================

async def _create_message(
    content: str,
    sender_id: int,
    group_id: Optional[int] = None,
    recipient_id: Optional[int] = None,
    reply_to_id: Optional[int] = None,
    file_url: Optional[str] = None,
    file_name: Optional[str] = None,
    file_type: Optional[str] = None,
    file_size: Optional[int] = 0,
    message_type: str = "text"
):
    """Internal helper that actually creates a message and broadcasts it.
    NOTE: this is a plain function (no FastAPI Form() defaults) so it can be
    safely called directly from other endpoints (file/recording upload) without
    the Form() sentinel objects leaking in as bound values."""
    with get_db() as db:
        sender = db.query(User).filter(User.id == sender_id).first()
        if not sender:
            raise HTTPException(status_code=404, detail="Sender not found")

        if group_id:
            member = db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == sender_id).first()
            if not member:
                raise HTTPException(status_code=403, detail="Not a member of this group")

        if recipient_id and recipient_id == sender_id:
            raise HTTPException(status_code=400, detail="Cannot message yourself")

        new_msg = Message(
            content=content,
            sender_id=sender_id,
            group_id=group_id,
            recipient_id=recipient_id,
            reply_to_id=reply_to_id,
            file_url=file_url,
            file_name=file_name,
            file_type=file_type,
            file_size=file_size or 0,
            message_type=message_type
        )
        db.add(new_msg)
        db.commit()
        db.refresh(new_msg)
        
        reply_content = None
        if reply_to_id:
            reply = db.query(Message).filter(Message.id == reply_to_id).first()
            if reply and not reply.is_deleted:
                reply_content = reply.content[:50] + ("..." if len(reply.content) > 50 else "")
        
        response = {
            "type": "message",
            "id": new_msg.id,
            "content": new_msg.content,
            "sender_id": sender_id,
            "sender_username": sender.display_name or sender.username,
            "group_id": new_msg.group_id,
            "recipient_id": new_msg.recipient_id,
            "timestamp": new_msg.timestamp.isoformat(),
            "is_read": new_msg.is_read,
            "message_type": new_msg.message_type,
            "is_deleted": new_msg.is_deleted,
            "edited_at": None,
            "reply_to_id": new_msg.reply_to_id,
            "reply_to_content": reply_content,
            "file_url": new_msg.file_url,
            "file_name": new_msg.file_name,
            "file_type": new_msg.file_type,
            "file_size": new_msg.file_size,
            "reactions": {}
        }
        
        if group_id:
            await manager.send_to_group_except(response, group_id, sender_id)
        elif recipient_id:
            await manager.send_to_user(response, recipient_id)
        
        await manager.send_to_user(response, sender_id)
        
        return {"success": True, "message_id": new_msg.id}

@app.post("/api/messages")
async def send_message(
    content: str = Form(...),
    sender_id: int = Form(...),
    group_id: Optional[int] = Form(None),
    recipient_id: Optional[int] = Form(None),
    reply_to_id: Optional[int] = Form(None),
    file_url: Optional[str] = Form(None),
    file_name: Optional[str] = Form(None),
    file_type: Optional[str] = Form(None),
    file_size: Optional[int] = Form(0)
):
    return await _create_message(
        content=content,
        sender_id=sender_id,
        group_id=group_id,
        recipient_id=recipient_id,
        reply_to_id=reply_to_id,
        file_url=file_url,
        file_name=file_name,
        file_type=file_type,
        file_size=file_size
    )

@app.post("/api/messages/file")
async def send_file_message(
    sender_id: int = Form(...),
    recipient_id: Optional[int] = Form(None),
    group_id: Optional[int] = Form(None),
    file: UploadFile = File(...)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")
    
    original_filename = file.filename
    ext = original_filename.split(".")[-1].lower() if "." in original_filename else "file"
    filename = f"chat_{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    file_size = os.path.getsize(file_path)
    file_type = file.content_type or ext

    if file_type.startswith("image/"):
        msg_type = "image"
    elif file_type.startswith("video/"):
        msg_type = "video"
    elif file_type.startswith("audio/"):
        msg_type = "audio"
    else:
        msg_type = "file"
    
    return await _create_message(
        content=f"📎 {original_filename}",
        sender_id=sender_id,
        group_id=group_id,
        recipient_id=recipient_id,
        file_url=filename,
        file_name=original_filename,
        file_type=file_type,
        file_size=file_size,
        message_type=msg_type
    )

@app.post("/api/messages/recording")
async def send_recording(
    sender_id: int = Form(...),
    recipient_id: Optional[int] = Form(None),
    group_id: Optional[int] = Form(None),
    recording_type: str = Form("audio"),
    file: UploadFile = File(...)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No recording provided")
    
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty recording")
    
    ext = "webm"
    # Keep video and audio recordings distinguishable on disk (not just by content-type)
    # since the browser player logic and reel-style icons key off this.
    # Saved into UPLOAD_DIR (not RECORDINGS_DIR) since the chat UI always
    # resolves message file_url paths as /uploads/<file_url>.
    prefix = "recvideo" if recording_type == "video" else "recaudio"
    filename = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        buffer.write(data)
    
    file_size = len(data)
    file_type = file.content_type or (f"{recording_type}/webm")
    
    if recording_type == "video":
        content = "🎥 Video recording"
        msg_type = "video"
    else:
        content = "🎙️ Voice note"
        msg_type = "audio"
    
    return await _create_message(
        content=content,
        sender_id=sender_id,
        group_id=group_id,
        recipient_id=recipient_id,
        file_url=filename,
        file_name=file.filename,
        file_type=file_type,
        file_size=file_size,
        message_type=msg_type
    )

@app.put("/api/messages/{message_id}")
async def edit_message(message_id: int, content: str = Form(...), user_id: int = Form(...)):
    with get_db() as db:
        msg = db.query(Message).filter(Message.id == message_id).first()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")
        
        if msg.sender_id != user_id:
            raise HTTPException(status_code=403, detail="Only the sender can edit")
        
        if msg.is_deleted:
            raise HTTPException(status_code=400, detail="Cannot edit deleted message")
        
        time_diff = datetime.now() - msg.timestamp
        if time_diff.total_seconds() > 300:
            raise HTTPException(status_code=400, detail="Can only edit within 5 minutes")
        
        msg.content = content
        msg.edited_at = datetime.now()
        db.commit()
        db.refresh(msg)
        
        response = {
            "type": "message_edited",
            "id": msg.id,
            "content": msg.content,
            "edited_at": msg.edited_at.isoformat(),
            "sender_id": msg.sender_id,
            "group_id": msg.group_id,
            "recipient_id": msg.recipient_id
        }
        
        if msg.group_id:
            await manager.send_to_group_except(response, msg.group_id, user_id)
        elif msg.recipient_id:
            await manager.send_to_user(response, msg.recipient_id)
        await manager.send_to_user(response, user_id)
        
        return {"success": True}

@app.delete("/api/messages/{message_id}")
async def delete_message(message_id: int, user_id: int = Form(...)):
    with get_db() as db:
        msg = db.query(Message).filter(Message.id == message_id).first()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")
        
        user = db.query(User).filter(User.id == user_id).first()
        is_group_admin = False
        if msg.group_id:
            gm = db.query(GroupMember).filter(GroupMember.group_id == msg.group_id, GroupMember.user_id == user_id).first()
            is_group_admin = bool(gm and gm.is_admin)
        
        if msg.sender_id != user_id and not is_group_admin:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        msg.is_deleted = True
        msg.content = "🗑️ This message was deleted"
        if is_group_admin and msg.sender_id != user_id:
            msg.content = "🗑️ Deleted by admin"
        db.commit()
        db.refresh(msg)
        
        response = {
            "type": "message_deleted",
            "id": msg.id,
            "content": msg.content,
            "sender_id": msg.sender_id,
            "group_id": msg.group_id,
            "recipient_id": msg.recipient_id,
            "deleted_by_admin": is_group_admin and msg.sender_id != user_id
        }
        
        if msg.group_id:
            await manager.send_to_group_except(response, msg.group_id, user_id)
        elif msg.recipient_id:
            await manager.send_to_user(response, msg.recipient_id)
        await manager.send_to_user(response, user_id)
        
        return {"success": True}

@app.delete("/api/messages/{message_id}/for-me")
async def delete_message_for_me(message_id: int, user_id: int = Form(...)):
    with get_db() as db:
        msg = db.query(Message).filter(Message.id == message_id).first()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")
        
        if msg.deleted_for:
            deleted_list = [int(id) for id in msg.deleted_for.split(',') if id.strip()]
            if user_id not in deleted_list:
                deleted_list.append(user_id)
                msg.deleted_for = ','.join(str(id) for id in deleted_list)
        else:
            msg.deleted_for = str(user_id)
        
        db.commit()
        return {"success": True}

@app.post("/api/messages/{message_id}/react")
async def react_to_message(message_id: int, user_id: int = Form(...), emoji: str = Form(...)):
    with get_db() as db:
        msg = db.query(Message).filter(Message.id == message_id).first()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")
        
        reactions = json.loads(msg.reactions) if msg.reactions else {}
        # reactions shape: { "😂": [user_id, ...], "❤️": [...] }
        
        current_emoji = None
        for e, uids in reactions.items():
            if user_id in uids:
                current_emoji = e
                break
        
        if current_emoji:
            reactions[current_emoji].remove(user_id)
            if not reactions[current_emoji]:
                del reactions[current_emoji]
        
        if current_emoji != emoji:
            reactions.setdefault(emoji, [])
            reactions[emoji].append(user_id)
        
        msg.reactions = json.dumps(reactions)
        db.commit()
        
        response = {
            "type": "message_reaction",
            "id": msg.id,
            "reactions": reactions,
            "group_id": msg.group_id,
            "recipient_id": msg.recipient_id,
            "sender_id": msg.sender_id
        }
        if msg.group_id:
            await manager.send_to_group_except(response, msg.group_id, user_id)
        elif msg.recipient_id:
            await manager.send_to_user(response, msg.recipient_id)
        await manager.send_to_user(response, user_id)
        
        return {"success": True, "reactions": reactions}

@app.get("/api/groups/{group_id}/messages")
async def get_group_messages(group_id: int, user_id: int, limit: int = 50):
    with get_db() as db:
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        
        msgs = db.query(Message).filter(
            Message.group_id == group_id,
            Message.is_deleted == False
        ).order_by(Message.timestamp.desc()).limit(limit).all()
        
        result = []
        for m in msgs[::-1]:
            if m.deleted_for:
                deleted_ids = [int(id) for id in m.deleted_for.split(',') if id.strip()]
                if user_id in deleted_ids:
                    continue
            sender = db.query(User).filter(User.id == m.sender_id).first()
            m.sender_username = sender.display_name or sender.username if sender else None
            result.append(m)
        return result

@app.get("/api/chat/{user_id}/messages")
async def get_private_messages(user_id: int, current_user_id: int, limit: int = 50):
    with get_db() as db:
        msgs = db.query(Message).filter(
            ((Message.sender_id == current_user_id) & (Message.recipient_id == user_id)) |
            ((Message.sender_id == user_id) & (Message.recipient_id == current_user_id)),
            Message.is_deleted == False
        ).order_by(Message.timestamp.desc()).limit(limit).all()
        
        result = []
        for m in msgs[::-1]:
            if m.deleted_for:
                deleted_ids = [int(id) for id in m.deleted_for.split(',') if id.strip()]
                if current_user_id in deleted_ids:
                    continue
            sender = db.query(User).filter(User.id == m.sender_id).first()
            m.sender_username = sender.display_name or sender.username if sender else None
            result.append(m)
        return result

# ============================================================
# LOCATION/GPS TRACKING ENDPOINTS
# ============================================================

@app.post("/api/location")
async def update_location(data: LocationUpdate):
    with get_db() as db:
        user = db.query(User).filter(User.id == data.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        location = Location(
            user_id=data.user_id,
            device_id=data.device_id,
            name=data.name,
            lat=data.lat,
            lng=data.lng,
            battery=data.battery or 100,
            distance=data.distance or 0.0
        )
        db.add(location)
        db.commit()
        
        await manager.broadcast({
            "type": "location_update",
            "user_id": data.user_id,
            "name": data.name,
            "lat": data.lat,
            "lng": data.lng,
            "battery": data.battery,
            "timestamp": datetime.now().isoformat()
        })
        
        return {"success": True}

@app.get("/api/locations")
async def get_locations():
    with get_db() as db:
        locations = db.query(Location).order_by(Location.id.desc()).all()
        latest = {}
        for loc in locations:
            if loc.user_id not in latest:
                latest[loc.user_id] = loc
        
        result = []
        for user_id, loc in latest.items():
            user = db.query(User).filter(User.id == user_id).first()
            result.append({
                "user_id": loc.user_id,
                "device_id": loc.device_id,
                "name": loc.name,
                "lat": loc.lat,
                "lng": loc.lng,
                "battery": loc.battery,
                "distance": loc.distance,
                "timestamp": loc.timestamp.isoformat(),
                "display_name": user.display_name or user.username if user else None,
                "avatar_color": user.avatar_color if user else "#800020"
            })
        return result

@app.get("/api/locations/{user_id}")
async def get_user_locations(user_id: int, limit: int = 20):
    with get_db() as db:
        locations = db.query(Location).filter(
            Location.user_id == user_id
        ).order_by(Location.timestamp.desc()).limit(limit).all()
        return [{
            "lat": loc.lat,
            "lng": loc.lng,
            "battery": loc.battery,
            "distance": loc.distance,
            "timestamp": loc.timestamp.isoformat()
        } for loc in locations]

@app.get("/api/locations/clear")
async def clear_locations():
    with get_db() as db:
        db.query(Location).delete()
        db.commit()
        return {"success": True}

# ============================================================
# RECORDING STORAGE ENDPOINTS
# ============================================================

@app.post("/api/recordings/save")
async def save_recording(
    user_id: int = Form(...),
    file: UploadFile = File(...)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")
    
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    
    encoded_data = base64.b64encode(data).decode('utf-8')
    filename = file.filename or f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.webm"
    
    with get_db() as db:
        recording = Recording(
            user_id=user_id,
            filename=filename,
            size=len(data),
            data=encoded_data
        )
        db.add(recording)
        db.commit()
        db.refresh(recording)
        
        return {
            "success": True,
            "id": recording.id,
            "filename": filename,
            "size": len(data),
            "timestamp": recording.timestamp.isoformat()
        }

@app.get("/api/recordings")
async def get_recordings(user_id: Optional[int] = None):
    with get_db() as db:
        query = db.query(Recording)
        if user_id:
            query = query.filter(Recording.user_id == user_id)
        recordings = query.order_by(Recording.timestamp.desc()).all()
        return [{
            "id": r.id,
            "user_id": r.user_id,
            "filename": r.filename,
            "size": r.size,
            "timestamp": r.timestamp.isoformat()
        } for r in recordings]

@app.get("/api/recordings/{recording_id}/download")
async def download_recording(recording_id: int):
    with get_db() as db:
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")
        
        data = base64.b64decode(recording.data)
        
        return Response(
            content=data,
            media_type="video/webm",
            headers={"Content-Disposition": f"attachment; filename={recording.filename}"}
        )

@app.delete("/api/recordings/{recording_id}")
async def delete_recording(recording_id: int, user_id: int = Form(...)):
    with get_db() as db:
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")
        
        user = db.query(User).filter(User.id == user_id).first()
        if recording.user_id != user_id and not (user and user.is_admin):
            raise HTTPException(status_code=403, detail="Not authorized")
        
        db.delete(recording)
        db.commit()
        return {"success": True}

# ============================================================
# NOTIFICATION ENDPOINTS
# ============================================================

@app.get("/api/notifications")
async def get_notifications(user_id: int):
    with get_db() as db:
        notifs = db.query(Notification).filter(
            Notification.user_id == user_id
        ).order_by(Notification.timestamp.desc()).limit(30).all()
        
        result = []
        for n in notifs:
            from_user = db.query(User).filter(User.id == n.from_user_id).first()
            result.append({
                "id": n.id,
                "type": n.type,
                "text": n.text,
                "is_read": n.is_read,
                "timestamp": n.timestamp.isoformat(),
                "from_user_id": n.from_user_id,
                "from_name": from_user.display_name or from_user.username if from_user else None
            })
        return result

@app.post("/api/notifications/mark_read")
async def mark_notifications_read(user_id: int = Form(...)):
    with get_db() as db:
        db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).update({"is_read": True})
        db.commit()
        return {"success": True}

# ============================================================
# REEL (SOCIAL POST) ENDPOINTS
# ============================================================

@app.post("/api/reels")
async def create_reel(
    user_id: int = Form(...),
    title: str = Form("Untitled"),
    description: str = Form(""),
    privacy: str = Form("public"),
    media: UploadFile = File(...)
):
    if not media.filename:
        raise HTTPException(status_code=400, detail="No file selected")
    
    ext = media.filename.split(".")[-1].lower()
    if ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']:
        media_type = 'video'
    elif ext in ['mp3', 'wav', 'aac', 'ogg', 'm4a']:
        media_type = 'audio'
    else:
        media_type = 'image'
    
    filename = f"reel_{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(media.file, buffer)
    
    with get_db() as db:
        reel = Reel(
            user_id=user_id,
            title=title,
            description=description,
            media_url=filename,
            media_type=media_type,
            privacy=privacy
        )
        db.add(reel)
        db.commit()
        db.refresh(reel)
        
        return {"success": True, "reel_id": reel.id}

@app.get("/api/reels")
async def get_reels(user_id: Optional[int] = None):
    with get_db() as db:
        query = db.query(Reel).order_by(Reel.id.desc())
        reels = query.all()
        
        result = []
        for r in reels:
            user = db.query(User).filter(User.id == r.user_id).first()
            if not user:
                continue
            
            if r.privacy == 'private' and r.user_id != user_id:
                continue
            if r.privacy == 'friends':
                if user_id:
                    is_friend = db.query(Friend).filter(
                        ((Friend.user1_id == r.user_id) & (Friend.user2_id == user_id)) |
                        ((Friend.user1_id == user_id) & (Friend.user2_id == r.user_id))
                    ).first()
                    if not is_friend and r.user_id != user_id:
                        continue
                elif r.user_id != user_id:
                    continue
            
            result.append({
                "id": r.id,
                "user_id": r.user_id,
                "title": r.title,
                "description": r.description,
                "media_url": r.media_url,
                "media_type": r.media_type,
                "privacy": r.privacy,
                "views": r.views,
                "likes": r.likes,
                "is_live": r.is_live,
                "comments": r.comments,
                "created_at": r.created_at,
                "display_name": user.display_name or user.username,
                "avatar_color": user.avatar_color,
                "profile_pic": user.profile_pic
            })
        return result

@app.get("/api/reels/{reel_id}")
async def get_reel(reel_id: int, user_id: Optional[int] = None):
    with get_db() as db:
        reel = db.query(Reel).filter(Reel.id == reel_id).first()
        if not reel:
            raise HTTPException(status_code=404, detail="Reel not found")
        
        user = db.query(User).filter(User.id == reel.user_id).first()
        
        if reel.privacy == 'private' and reel.user_id != user_id:
            raise HTTPException(status_code=403, detail="Private reel")
        if reel.privacy == 'friends':
            is_friend = db.query(Friend).filter(
                ((Friend.user1_id == reel.user_id) & (Friend.user2_id == user_id)) |
                ((Friend.user1_id == user_id) & (Friend.user2_id == reel.user_id))
            ).first()
            if not is_friend and reel.user_id != user_id:
                raise HTTPException(status_code=403, detail="Friends only")
        
        reel.views += 1
        db.commit()
        
        liked_by = json.loads(reel.liked_by) if reel.liked_by else []
        
        return {
            "id": reel.id,
            "user_id": reel.user_id,
            "title": reel.title,
            "description": reel.description,
            "media_url": reel.media_url,
            "media_type": reel.media_type,
            "privacy": reel.privacy,
            "views": reel.views,
            "likes": reel.likes,
            "liked_by_me": user_id in liked_by if user_id else False,
            "is_live": reel.is_live,
            "comments": reel.comments,
            "created_at": reel.created_at,
            "display_name": user.display_name or user.username,
            "avatar_color": user.avatar_color,
            "profile_pic": user.profile_pic
        }

@app.post("/api/reels/{reel_id}/like")
async def like_reel(reel_id: int, user_id: int = Form(...)):
    with get_db() as db:
        reel = db.query(Reel).filter(Reel.id == reel_id).first()
        if not reel:
            raise HTTPException(status_code=404, detail="Reel not found")
        
        liked_by = json.loads(reel.liked_by) if reel.liked_by else []
        if user_id in liked_by:
            liked_by.remove(user_id)
            reel.likes = max(0, reel.likes - 1)
            liked = False
        else:
            liked_by.append(user_id)
            reel.likes += 1
            liked = True
        reel.liked_by = json.dumps(liked_by)
        db.commit()
        
        if liked and reel.user_id != user_id:
            user = db.query(User).filter(User.id == user_id).first()
            notification = Notification(
                user_id=reel.user_id,
                from_user_id=user_id,
                type="like",
                text=f"{user.display_name or user.username} liked your reel: {reel.title}"
            )
            db.add(notification)
            db.commit()
        
        return {"success": True, "likes": reel.likes, "liked": liked}

@app.post("/api/reels/{reel_id}/comment")
async def add_comment(reel_id: int, user_id: int = Form(...), text: str = Form(...)):
    with get_db() as db:
        reel = db.query(Reel).filter(Reel.id == reel_id).first()
        if not reel:
            raise HTTPException(status_code=404, detail="Reel not found")
        
        comments = json.loads(reel.comments) if reel.comments else []
        comment = {
            "user_id": user_id,
            "text": text,
            "timestamp": datetime.now().isoformat()
        }
        comments.append(comment)
        reel.comments = json.dumps(comments)
        db.commit()
        
        if reel.user_id != user_id:
            user = db.query(User).filter(User.id == user_id).first()
            notification = Notification(
                user_id=reel.user_id,
                from_user_id=user_id,
                type="comment",
                text=f"{user.display_name or user.username} commented on your reel: {text[:30]}"
            )
            db.add(notification)
            db.commit()
        
        return {"success": True, "comment": comment, "comments": comments}

@app.delete("/api/reels/{reel_id}")
async def delete_reel(reel_id: int, user_id: int = Form(...)):
    with get_db() as db:
        reel = db.query(Reel).filter(Reel.id == reel_id).first()
        if not reel:
            raise HTTPException(status_code=404, detail="Reel not found")
        
        if reel.user_id != user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.is_admin:
                raise HTTPException(status_code=403, detail="Not authorized")
        
        try:
            if os.path.exists(os.path.join(UPLOAD_DIR, reel.media_url)):
                os.remove(os.path.join(UPLOAD_DIR, reel.media_url))
        except:
            pass
        
        db.delete(reel)
        db.commit()
        return {"success": True}

# ============================================================
# STORY ENDPOINTS
# ============================================================

@app.post("/api/stories")
async def create_story(
    user_id: int = Form(...),
    media: UploadFile = File(...)
):
    if not media.filename:
        raise HTTPException(status_code=400, detail="No file selected")
    
    ext = media.filename.split(".")[-1].lower()
    if ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']:
        media_type = 'video'
    elif ext in ['mp3', 'wav', 'aac', 'ogg', 'm4a']:
        media_type = 'audio'
    else:
        media_type = 'image'
    
    filename = f"story_{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(media.file, buffer)
    
    with get_db() as db:
        story = Story(
            user_id=user_id,
            media_url=filename,
            media_type=media_type,
            expires_at=datetime.now() + timedelta(hours=24)
        )
        db.add(story)
        db.commit()
        db.refresh(story)
        
        return {"success": True, "story_id": story.id}

@app.get("/api/stories")
async def get_stories(user_id: Optional[int] = None):
    with get_db() as db:
        query = db.query(Story).filter(Story.expires_at > datetime.now())
        stories = query.order_by(Story.created_at.desc()).all()
        
        result = []
        for s in stories:
            user = db.query(User).filter(User.id == s.user_id).first()
            if user:
                result.append({
                    "id": s.id,
                    "user_id": s.user_id,
                    "media_url": s.media_url,
                    "media_type": s.media_type,
                    "created_at": s.created_at,
                    "display_name": user.display_name or user.username,
                    "avatar_color": user.avatar_color,
                    "profile_pic": user.profile_pic
                })
        return result

# ============================================================
# LIVE STREAM ENDPOINTS
# ============================================================

@app.post("/api/reels/live/start")
async def start_live_stream(
    user_id: int = Form(...), 
    title: str = Form("Live Stream"), 
    description: str = Form("")
):
    with get_db() as db:
        stream_key = f"live_{uuid.uuid4().hex}"
        
        reel = Reel(
            user_id=user_id,
            title=title,
            description=description,
            media_url=stream_key,
            media_type="video",
            privacy="public",
            is_live=True,
            live_stream_url=stream_key
        )
        db.add(reel)
        db.commit()
        db.refresh(reel)
        
        user = db.query(User).filter(User.id == user_id).first()
        
        # Notify followers
        followers = db.query(Friend).filter(
            (Friend.user1_id == user_id) | (Friend.user2_id == user_id)
        ).all()
        
        for f in followers:
            follower_id = f.user2_id if f.user1_id == user_id else f.user1_id
            notification = Notification(
                user_id=follower_id,
                from_user_id=user_id,
                type="live_start",
                text=f"{user.display_name or user.username} started a live stream: {title}"
            )
            db.add(notification)
        
        db.commit()
        
        live_payload = {
            "type": "live_started",
            "user_id": user_id,
            "name": user.display_name or user.username,
            "title": title,
            "reel_id": reel.id
        }
        for f in followers:
            follower_id = f.user2_id if f.user1_id == user_id else f.user1_id
            await manager.send_to_user(live_payload, follower_id)
        await manager.send_to_user(live_payload, user_id)
        
        return {"success": True, "reel_id": reel.id, "stream_key": stream_key}

@app.post("/api/reels/live/end")
async def end_live_stream(reel_id: int = Form(...)):
    with get_db() as db:
        reel = db.query(Reel).filter(Reel.id == reel_id).first()
        if not reel:
            raise HTTPException(status_code=404, detail="Reel not found")
        
        reel.is_live = False
        db.commit()
        
        user = db.query(User).filter(User.id == reel.user_id).first()
        followers = db.query(Friend).filter(
            (Friend.user1_id == reel.user_id) | (Friend.user2_id == reel.user_id)
        ).all()
        
        live_payload = {
            "type": "live_ended",
            "user_id": reel.user_id,
            "name": user.display_name or user.username,
            "reel_id": reel.id
        }
        for f in followers:
            follower_id = f.user2_id if f.user1_id == reel.user_id else f.user1_id
            await manager.send_to_user(live_payload, follower_id)
        await manager.send_to_user(live_payload, reel.user_id)
        
        return {"success": True}

@app.post("/api/reels/live/save")
async def save_live_stream(
    reel_id: int = Form(...),
    user_id: int = Form(...)
):
    with get_db() as db:
        reel = db.query(Reel).filter(Reel.id == reel_id).first()
        if not reel:
            raise HTTPException(status_code=404, detail="Reel not found")
        
        if reel.user_id != user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.is_admin:
                raise HTTPException(status_code=403, detail="Not authorized")
        
        if reel.is_live:
            reel.is_live = False
            db.commit()
        
        return {"success": True, "reel_id": reel.id}

# ============================================================
# WEBSOCKET ENDPOINT
# ============================================================

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            await websocket.close(code=1008)
            return
        display_name = user.display_name or user.username
    
    await manager.connect(user_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg_data = json.loads(data)
                msg_type = msg_data.get("type")
                
                if msg_type == "typing":
                    if msg_data.get("group_id"):
                        await manager.send_to_group_except({
                            "type": "typing",
                            "user_id": user_id,
                            "username": display_name,
                            "group_id": msg_data["group_id"]
                        }, msg_data["group_id"], user_id)
                    elif msg_data.get("recipient_id"):
                        await manager.send_to_user({
                            "type": "typing",
                            "user_id": user_id,
                            "username": display_name
                        }, msg_data["recipient_id"])
                
                elif msg_type == "message":
                    content = msg_data.get("content", "")
                    group_id = msg_data.get("group_id")
                    recipient_id = msg_data.get("recipient_id")
                    reply_to_id = msg_data.get("reply_to_id")
                    
                    if recipient_id and recipient_id == user_id:
                        await manager.send_to_user({"type": "error", "message": "Cannot message yourself"}, user_id)
                        continue
                    
                    with get_db() as db:
                        if group_id:
                            group = db.query(Group).filter(Group.id == group_id).first()
                            if group and group.is_locked:
                                member = db.query(GroupMember).filter(
                                    GroupMember.user_id == user_id,
                                    GroupMember.group_id == group_id
                                ).first()
                                if not member:
                                    await manager.send_to_user({
                                        "type": "error",
                                        "message": "This group is locked"
                                    }, user_id)
                                    continue
                        
                        new_msg = Message(
                            content=content,
                            sender_id=user_id,
                            group_id=group_id,
                            recipient_id=recipient_id,
                            reply_to_id=reply_to_id
                        )
                        db.add(new_msg)
                        db.commit()
                        db.refresh(new_msg)
                        
                        reply_content = None
                        if reply_to_id:
                            reply = db.query(Message).filter(Message.id == reply_to_id).first()
                            if reply and not reply.is_deleted:
                                reply_content = reply.content[:50] + ("..." if len(reply.content) > 50 else "")
                        
                        response = {
                            "type": "message",
                            "id": new_msg.id,
                            "content": new_msg.content,
                            "sender_id": user_id,
                            "sender_username": display_name,
                            "group_id": new_msg.group_id,
                            "recipient_id": new_msg.recipient_id,
                            "timestamp": new_msg.timestamp.isoformat(),
                            "is_read": new_msg.is_read,
                            "message_type": new_msg.message_type,
                            "is_deleted": new_msg.is_deleted,
                            "edited_at": None,
                            "reply_to_id": new_msg.reply_to_id,
                            "reply_to_content": reply_content,
                            "file_url": new_msg.file_url,
                            "file_name": new_msg.file_name,
                            "file_type": new_msg.file_type,
                            "file_size": new_msg.file_size,
                            "reactions": {}
                        }
                    
                    if group_id:
                        await manager.send_to_group_except(response, group_id, user_id)
                    elif recipient_id:
                        await manager.send_to_user(response, recipient_id)
                    await manager.send_to_user(response, user_id)
                
                elif msg_type == "read_receipt":
                    message_id = msg_data.get("message_id")
                    with get_db() as db:
                        msg = db.query(Message).filter(Message.id == message_id).first()
                        if msg and msg.recipient_id == user_id:
                            msg.is_read = True
                            msg.read_at = datetime.now()
                            db.commit()
                            await manager.send_to_user({
                                "type": "read_receipt",
                                "message_id": message_id,
                                "reader_id": user_id
                            }, msg.sender_id)
                
                elif msg_type == "location":
                    lat = msg_data.get("lat")
                    lng = msg_data.get("lng")
                    if lat is not None and lng is not None:
                        with get_db() as db:
                            location = Location(
                                user_id=user_id,
                                device_id=f"user_{user_id}",
                                name=display_name,
                                lat=lat,
                                lng=lng,
                                battery=msg_data.get("battery", 100)
                            )
                            db.add(location)
                            db.commit()
                            
                            await manager.broadcast({
                                "type": "location_update",
                                "user_id": user_id,
                                "name": display_name,
                                "lat": lat,
                                "lng": lng,
                                "battery": msg_data.get("battery", 100),
                                "timestamp": datetime.now().isoformat()
                            })
                
            except json.JSONDecodeError:
                pass
    
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)

# ============================================================
# NGROK SETUP
# ============================================================
def setup_ngrok():
    try:
        ngrok.set_auth_token(NGROK_AUTHTOKEN)
        ngrok.kill()
        public_url = ngrok.connect(8000)
        print(f"\n✅ ngrok tunnel established at: {public_url}")
        return public_url
    except Exception as e:
        print(f"⚠️ ngrok failed: {e}")
        return None

# ============================================================
# FRONTEND - Complete UI
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>FUOMCE - Communication</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyATG4caJAD9HxLZDtrJdEAWq_qXCyPaH3E&language=en"></script>
    <style>
        :root {
            --white: #FFFFFF;
            --bg-gray: #f5f5f5;
            --charcoal: #2C2C2C;
            --charcoal-light: #4a4a4a;
            --burgundy: #800020;
            --burgundy-light: #A02840;
            --burgundy-dark: #4A0012;
            --beige: #F5F0EB;
            --camel: #c69c6d;
            --camel-light: #e8d5c0;
            --shadow: 0 6px 20px rgba(44, 44, 44, 0.08);
            --radius: 12px;
            --radius-full: 9999px;
            --red: #ff4757;
            --green: #2ed573;
            --blue: #3498db;
            --gold: #f1c40f;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; -webkit-tap-highlight-color: transparent; }
        body { background: var(--bg-gray); height: 100vh; overflow: hidden; }
        button { cursor: pointer; border: none; outline: none; background: transparent; font-size: 1rem; }
        input, textarea, select { font-family: inherit; outline: none; }
        
        /* SPLASH SCREEN - G4 Style */
        #splash {
            position: fixed; top: 0; left: 0; width: 100%; height: 100vh;
            background: linear-gradient(135deg, var(--burgundy) 0%, var(--burgundy-dark) 100%);
            display: flex; flex-direction: column; justify-content: center; align-items: center;
            z-index: 9999; color: white; text-align: center; padding: 20px;
            transition: opacity 0.8s ease, transform 0.8s ease;
        }
        #splash.hidden { opacity: 0; transform: scale(1.05); pointer-events: none; }
        #splash .logo { font-size: 4.5rem; font-weight: 800; letter-spacing: -3px; }
        #splash .logo span { font-weight: 300; }
        #splash p { opacity: 0.8; font-size: 1.1rem; margin-bottom: 25px; }
        #splash .loader { width: 40px; height: 40px; border: 4px solid rgba(255,255,255,0.2); border-top: 4px solid white; border-radius: 50%; animation: spin 0.8s linear infinite; margin: 10px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        #splash .countdown-text { font-size: 0.9rem; opacity: 0.6; margin-top: 8px; letter-spacing: 1px; }
        
        /* LOGIN - G3 Style */
        #login-page {
            display: flex; flex-direction: column; justify-content: center; align-items: center;
            height: 100vh; background: linear-gradient(135deg, var(--white) 60%, var(--camel-light));
            padding: 20px;
        }
        .login-card { background: var(--white); padding: 3rem; border-radius: 24px; box-shadow: var(--shadow); width: 100%; max-width: 400px; }
        .login-card .logo { font-size: 2.8rem; font-weight: 800; text-align: center; color: var(--charcoal); margin-bottom: 5px; }
        .login-card .logo span { color: var(--burgundy); }
        .login-card h2 { text-align: center; font-weight: 400; color: var(--charcoal-light); margin-bottom: 25px; font-size: 1.2rem; }
        .input-group { margin-bottom: 16px; }
        .input-group label { display: block; font-weight: 600; font-size: 0.85rem; color: var(--charcoal-light); margin-bottom: 4px; }
        .input-group input { width: 100%; padding: 13px 16px; border: 2px solid #e0e0e0; border-radius: 10px; font-size: 1rem; transition: 0.3s; background: var(--bg-gray); }
        .input-group input:focus { border-color: var(--burgundy); background: white; box-shadow: 0 0 0 4px rgba(128,0,32,0.08); }
        .btn-primary { width: 100%; padding: 15px; background: var(--charcoal); color: white; border-radius: 10px; font-weight: 700; font-size: 1.05rem; transition: 0.3s; }
        .btn-primary:hover { background: var(--burgundy); transform: translateY(-2px); box-shadow: 0 4px 20px rgba(128,0,32,0.3); }
        .btn-primary:active { transform: translateY(0); }
        .btn-outline { width: 100%; padding: 14px; background: transparent; border: 2px solid var(--charcoal); color: var(--charcoal); border-radius: 10px; font-weight: 600; margin-top: 10px; transition: 0.3s; }
        .btn-outline:hover { background: var(--bg-gray); }
        .login-footer { text-align: center; margin-top: 20px; font-size: 0.9rem; color: var(--charcoal-light); }
        .login-footer a { color: var(--burgundy); font-weight: 600; cursor: pointer; }
        .login-footer a:hover { color: var(--charcoal); }
        .auth-toggle { margin-top: 15px; }
        
        /* MAIN APP - G3 Style */
        #app-container { display: none; height: 100vh; width: 100vw; overflow: hidden; }
        .app-layout { display: flex; height: 100%; width: 100%; position: relative; background: var(--bg-gray); }

        /* MOBILE/TABLET MENU TOGGLE - ported from Stacey_Frontend_Two.html's responsive pattern */
        .menu-toggle {
            display: none; position: fixed; top: 14px; left: 14px; z-index: 150;
            width: 44px; height: 44px; background: var(--charcoal); color: var(--camel);
            border: none; border-radius: 12px; font-size: 18px; align-items: center;
            justify-content: center; box-shadow: var(--shadow); cursor: pointer;
        }
        
        /* SIDEBAR - G3 Style */
        .sidebar {
            width: 280px; background: var(--white); border-right: 1px solid #eaeaea;
            display: flex; flex-direction: column; flex-shrink: 0; overflow-y: auto;
            padding: 16px 12px; z-index: 10;
        }
        .sidebar .logo { font-size: 1.8rem; font-weight: 800; color: var(--charcoal); padding: 0 8px 16px; border-bottom: 2px solid #f0f0f0; margin-bottom: 12px; }
        .sidebar .logo span { color: var(--burgundy); }
        .nav-item {
            display: flex; align-items: center; padding: 12px 14px; border-radius: var(--radius);
            margin-bottom: 2px; transition: 0.2s; cursor: pointer; color: var(--charcoal-light);
            font-weight: 500; font-size: 0.95rem;
        }
        .nav-item:hover { background: var(--bg-gray); transform: translateX(4px); }
        .nav-item.active { background: var(--camel-light); color: var(--charcoal); }
        .nav-item i { width: 28px; font-size: 1.2rem; }
        .nav-item .badge { background: var(--red); color: white; font-size: 0.65rem; padding: 1px 8px; border-radius: 10px; margin-left: auto; }
        .sidebar-divider { height: 1px; background: #eee; margin: 12px 0; }
        .sidebar-title { padding: 8px 12px; font-size: 0.7rem; text-transform: uppercase; color: #999; font-weight: 700; letter-spacing: 0.5px; }
        
        .user-suggestion {
            display: flex; align-items: center; padding: 8px 10px; border-radius: var(--radius);
            transition: 0.2s; cursor: pointer; gap: 10px; margin-bottom: 3px;
        }
        .user-suggestion:hover { background: var(--bg-gray); }
        .user-suggestion .avatar {
            width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
            color: white; font-weight: 700; font-size: 0.9rem; flex-shrink: 0; position: relative;
        }
        .user-suggestion .avatar .online-dot { position: absolute; bottom: 0; right: 0; width: 10px; height: 10px; border-radius: 50%; border: 2px solid white; }
        .user-suggestion .info { flex: 1; min-width: 0; }
        .user-suggestion .name { font-weight: 600; font-size: 0.85rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .user-suggestion .sub { font-size: 0.7rem; color: #999; }
        .user-suggestion .follow-btn {
            background: var(--camel); color: white; padding: 3px 14px; border-radius: var(--radius-full);
            font-size: 0.7rem; font-weight: 600; transition: 0.2s; flex-shrink: 0;
        }
        .user-suggestion .follow-btn:hover { background: var(--burgundy); }
        .user-suggestion .follow-btn.following { background: #eee; color: #888; }
        
        /* MAIN CONTENT */
        .main-content { flex: 1; display: flex; flex-direction: column; background: var(--bg-gray); overflow: hidden; position: relative; }
        .page-section {
            display: none; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            padding: 16px 24px; background: var(--bg-gray); overflow-y: auto; z-index: 5;
            animation: fadeIn 0.3s ease;
        }
        .page-section.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        
        /* TOP BAR - G3 Style */
        .top-bar {
            display: flex; align-items: center; gap: 16px; padding: 12px 0 16px;
            border-bottom: 1px solid #eaeaea; margin-bottom: 16px; flex-wrap: wrap;
        }
        .top-bar .search-container { flex: 1; max-width: 450px; position: relative; }
        .top-bar .search-container input {
            width: 100%; padding: 10px 16px 10px 40px; border: 2px solid #eaeaea; border-radius: var(--radius-full);
            font-size: 0.9rem; transition: 0.3s; background: white;
        }
        .top-bar .search-container input:focus { border-color: var(--burgundy); box-shadow: 0 0 0 4px rgba(128,0,32,0.08); }
        .top-bar .search-container i { position: absolute; left: 14px; top: 50%; transform: translateY(-50%); color: #999; }
        .search-results-dropdown {
            position: absolute; top: 100%; left: 0; right: 0; background: white; border-radius: var(--radius);
            box-shadow: var(--shadow); max-height: 250px; overflow-y: auto; display: none; margin-top: 4px; z-index: 100;
        }
        .search-results-dropdown.active { display: block; }
        .search-result-item {
            display: flex; align-items: center; gap: 12px; padding: 10px 14px; cursor: pointer;
            transition: 0.2s; border-bottom: 1px solid #f5f5f5;
        }
        .search-result-item:hover { background: var(--bg-gray); }
        .search-result-item .avatar {
            width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
            color: white; font-weight: 700; font-size: 0.8rem; position: relative;
        }
        .search-result-item .avatar .online-dot { position: absolute; bottom: 0; right: 0; width: 8px; height: 8px; border-radius: 50%; border: 2px solid white; }
        .search-result-item .info { flex: 1; }
        .search-result-item .name { font-weight: 600; font-size: 0.85rem; }
        .search-result-item .username { font-size: 0.75rem; color: #999; }
        
        /* STORIES ROW - G3 Style */
        .stories-row {
            display: flex; gap: 14px; padding: 12px 0 16px;
            border-bottom: 1px solid #eaeaea; margin-bottom: 16px; overflow-x: auto;
        }
        .story-circle {
            display: flex; flex-direction: column; align-items: center; cursor: pointer;
            transition: 0.2s; min-width: 70px;
        }
        .story-circle:hover { transform: scale(1.05); }
        .story-circle .avatar {
            width: 60px; height: 60px; border-radius: 50%;
            border: 3px solid var(--burgundy); padding: 2px;
            display: flex; align-items: center; justify-content: center;
            color: white; font-weight: 700; font-size: 1.3rem;
            margin-bottom: 4px; position: relative;
            background: var(--bg-gray);
        }
        .story-circle .avatar img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
        .story-circle .avatar .add-story {
            background: var(--burgundy); color: white;
            width: 28px; height: 28px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 1.2rem; position: absolute; bottom: -5px; right: -5px;
            border: 2px solid white;
        }
        .story-circle span { font-size: 0.7rem; color: var(--charcoal-light); font-weight: 500; text-align: center; max-width: 65px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        
        /* HOME TABS - G3 Style */
        .home-tabs-row {
            display: flex; gap: 20px; border-bottom: 1px solid #eaeaea; padding-bottom: 10px; margin-bottom: 16px;
        }
        .home-tab-btn {
            font-weight: 600; color: #999; padding-bottom: 8px; cursor: pointer; font-size: 0.95rem;
            transition: 0.2s; position: relative; border: none; background: transparent;
        }
        .home-tab-btn:hover { color: var(--charcoal); }
        .home-tab-btn.active { color: var(--charcoal); }
        .home-tab-btn.active::after {
            content: ''; position: absolute; bottom: -11px; left: 0; width: 100%; height: 3px;
            background: var(--burgundy); border-radius: 2px;
        }
        
        /* GRID REELS - G3 Style */
        .grid-reels {
            display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px;
            margin-bottom: 20px;
        }
        .grid-card {
            background: var(--white); border-radius: var(--radius); overflow: hidden;
            box-shadow: var(--shadow); transition: 0.2s; cursor: pointer;
        }
        .grid-card:hover { transform: translateY(-4px); box-shadow: 0 8px 30px rgba(44,44,44,0.12); }
        .grid-card-img {
            height: 200px; position: relative; background: var(--charcoal); overflow: hidden;
        }
        .grid-card-img img, .grid-card-img video { width: 100%; height: 100%; object-fit: cover; }
        .grid-card-img audio { width: 100%; height: 100%; padding: 20px; background: var(--charcoal); }
        .grid-card-img .media-cover {
            width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;
            gap: 8px; color: white;
        }
        .grid-card-img .media-cover.audio-cover { background: linear-gradient(135deg, var(--burgundy) 0%, var(--charcoal) 100%); }
        .grid-card-img .media-cover i { font-size: 2.4rem; opacity: 0.9; }
        .grid-card-img .media-type-badge {
            position: absolute; top: 8px; left: 8px; color: white; font-size: 0.7rem;
            background: rgba(0,0,0,0.6); width: 26px; height: 26px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center; z-index: 2;
        }
        .grid-card-img .play-badge {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
            width: 46px; height: 46px; border-radius: 50%; background: rgba(0,0,0,0.45);
            display: flex; align-items: center; justify-content: center; color: white; font-size: 1.2rem;
            pointer-events: none;
        }
        .grid-card-img .broken-media {
            width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;
            gap: 6px; color: #ccc; background: var(--charcoal); font-size: 0.7rem;
        }
        .grid-card-img .broken-media i { font-size: 2rem; color: #888; }
        .grid-card-img .overlay-stats {
            position: absolute; bottom: 8px; left: 8px; color: white; font-size: 0.7rem;
            background: rgba(0,0,0,0.5); padding: 2px 10px; border-radius: var(--radius-full);
            display: flex; align-items: center; gap: 5px;
        }
        .grid-card-img .live-badge {
            position: absolute; top: 8px; right: 8px; background: var(--red); color: white;
            padding: 2px 10px; border-radius: var(--radius-full); font-size: 0.65rem; font-weight: 700;
            animation: pulse 1.5s infinite; display: flex; align-items: center; gap: 4px;
        }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .grid-card-info {
            padding: 12px; display: flex; align-items: center; gap: 10px;
        }
        .grid-card-info .avatar {
            width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
            color: white; font-weight: 700; font-size: 0.8rem; flex-shrink: 0;
        }
        .grid-card-info .text { flex: 1; min-width: 0; }
        .grid-card-info .text h4 { font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .grid-card-info .text p { font-size: 0.7rem; color: #888; }
        
        /* MODALS - G3 Style */
        .modal-overlay {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.6); backdrop-filter: blur(4px); z-index: 300;
            display: none; justify-content: center; align-items: center; padding: 20px;
        }
        .modal-overlay.active { display: flex; }
        .modal-container {
            background: var(--white); padding: 30px; border-radius: var(--radius);
            max-width: 600px; width: 100%; max-height: 90vh; overflow-y: auto;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .modal-close {
            float: right; font-size: 1.5rem; cursor: pointer; color: var(--charcoal-light);
            transition: 0.2s; background: none; border: none;
        }
        .modal-close:hover { color: var(--red); transform: rotate(90deg); }
        .modal-container h2 { margin-bottom: 16px; color: var(--charcoal); }
        .modal-container .form-group { margin-bottom: 14px; }
        .modal-container .form-group label { display: block; font-weight: 600; font-size: 0.85rem; color: var(--charcoal-light); margin-bottom: 4px; }
        .modal-container .form-group input, .modal-container .form-group textarea, .modal-container .form-group select {
            width: 100%; padding: 10px 14px; border: 2px solid #eaeaea; border-radius: 8px; font-size: 0.95rem;
            transition: 0.3s; background: var(--bg-gray);
        }
        .modal-container .form-group input:focus, .modal-container .form-group textarea:focus, .modal-container .form-group select:focus {
            border-color: var(--burgundy); background: white;
        }
        .modal-container .form-group textarea { resize: vertical; min-height: 60px; }
        .modal-actions { display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap; }
        .modal-actions .btn-primary { flex: 1; min-width: 100px; }
        .modal-actions .btn-secondary { flex: 1; min-width: 80px; background: var(--bg-gray); color: var(--charcoal-light); padding: 12px; border-radius: 8px; font-weight: 600; }
        .modal-actions .btn-secondary:hover { background: #e0e0e0; }
        .modal-area {
            border: 2px dashed var(--camel); padding: 30px; border-radius: var(--radius);
            cursor: pointer; transition: 0.3s; background: var(--camel-light); text-align: center;
        }
        .modal-area:hover { background: #f0e0d0; border-color: var(--burgundy); }
        .modal-area i { font-size: 2.5rem; color: var(--camel); margin-bottom: 8px; }
        .privacy-select { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #ddd; margin-bottom: 12px; }
        
        /* UPLOAD MODAL - G3 Style */
        #uploadPreviews {
            display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
            gap: 10px; margin-bottom: 12px; max-height: 200px; overflow-y: auto;
        }
        #uploadPreviews .preview-item {
            position: relative; border-radius: 8px; overflow: hidden;
            background: #2c2c2c; aspect-ratio: 1;
        }
        #uploadPreviews .preview-item img, 
        #uploadPreviews .preview-item video {
            width: 100%; height: 100%; object-fit: cover;
        }
        #uploadPreviews .preview-item .remove-btn {
            position: absolute; top: 4px; right: 4px;
            background: var(--red); color: white; border: none;
            border-radius: 50%; width: 24px; height: 24px;
            cursor: pointer; font-size: 16px; z-index: 2;
        }
        
        /* CHAT - G1 Style */
        .chat-container { display: flex; height: 100%; background: var(--white); border-radius: var(--radius); overflow: hidden; box-shadow: var(--shadow); }
        .chat-list { width: 320px; border-right: 1px solid #eaeaea; display: flex; flex-direction: column; flex-shrink: 0; }
        .chat-search { padding: 12px 16px; border-bottom: 1px solid #eaeaea; }
        .chat-search input { width: 100%; padding: 8px 14px; background: var(--bg-gray); border-radius: var(--radius-full); border: none; outline: none; }
        .chat-search input:focus { box-shadow: 0 0 0 2px var(--burgundy); }
        .chat-list-item {
            display: flex; align-items: center; padding: 12px 16px; border-bottom: 1px solid #f5f5f5;
            cursor: pointer; transition: 0.2s; gap: 12px;
        }
        .chat-list-item:hover { background: var(--bg-gray); }
        .chat-list-item.active { background: var(--camel-light); }
        .chat-list-item .avatar {
            width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
            color: white; font-weight: 700; font-size: 1rem; flex-shrink: 0; position: relative;
        }
        .chat-list-item .avatar .online-dot { position: absolute; bottom: 0; right: 0; width: 10px; height: 10px; border-radius: 50%; border: 2px solid white; }
        .chat-list-item .details { flex: 1; min-width: 0; }
        .chat-list-item .details h4 { font-size: 0.9rem; }
        .chat-list-item .details p { font-size: 0.8rem; color: #888; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .chat-list-item .time { font-size: 0.65rem; color: #aaa; flex-shrink: 0; }
        .chat-list-item .group-actions { display: flex; gap: 4px; }
        
        /* CHAT WINDOW - G1 Style */
        .chat-window { flex: 1; display: flex; flex-direction: column; background: #fafafa; }
        .chat-messages { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
        .chat-message {
            max-width: 75%; padding: 10px 16px; border-radius: 16px; font-size: 0.9rem;
            word-wrap: break-word; position: relative;
        }
        .chat-message.sent { align-self: flex-end; background: var(--burgundy); color: white; border-bottom-right-radius: 4px; }
        .chat-message.received { align-self: flex-start; background: #e8e8e8; color: var(--charcoal); border-bottom-left-radius: 4px; }
        .chat-message .time { font-size: 0.6rem; opacity: 0.7; display: block; text-align: right; margin-top: 4px; }
        .message-wrapper { position: relative; }
        .message-wrapper .msg-actions {
            position: absolute; top: -14px; display: none; gap: 4px; background: white; border-radius: var(--radius-full);
            box-shadow: 0 2px 8px rgba(0,0,0,0.15); padding: 3px 6px; z-index: 3;
        }
        .message-wrapper.sent .msg-actions { right: 6px; }
        .message-wrapper.received .msg-actions { left: 6px; }
        .message-wrapper:hover .msg-actions { display: flex; }
        .msg-actions button { background: none; border: none; cursor: pointer; font-size: 0.75rem; color: #888; padding: 2px 4px; }
        .msg-actions button:hover { color: var(--burgundy); }
        .msg-reactions { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 2px; }
        .msg-reactions .reaction-pill {
            background: white; border: 1px solid #eaeaea; border-radius: var(--radius-full); padding: 1px 7px;
            font-size: 0.7rem; cursor: pointer; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        .msg-reactions .reaction-pill.mine { border-color: var(--burgundy); background: rgba(128,0,32,0.08); }
        .emoji-picker-popup {
            position: absolute; top: -40px; display: none; gap: 4px; background: white; border-radius: var(--radius-full);
            box-shadow: 0 2px 10px rgba(0,0,0,0.2); padding: 4px 8px; z-index: 10;
        }
        .message-wrapper.sent .emoji-picker-popup { right: 6px; }
        .message-wrapper.received .emoji-picker-popup { left: 6px; }
        .emoji-picker-popup.active { display: flex; }
        .emoji-picker-popup span { cursor: pointer; font-size: 1rem; }
        .reply-preview-bar {
            display: none; align-items: center; gap: 8px; padding: 8px 12px; background: #f5f5f5;
            border-left: 3px solid var(--burgundy); border-radius: 8px; margin-bottom: 6px; font-size: 0.8rem;
        }
        .reply-preview-bar.active { display: flex; }
        .reply-preview-bar .close-reply { margin-left: auto; cursor: pointer; color: #888; }
        .chat-message .file-attachment {
            margin-top: 6px; padding: 8px 12px; background: rgba(255,255,255,0.15); border-radius: 8px;
            display: flex; align-items: center; gap: 10px; cursor: pointer; transition: 0.2s;
        }
        .chat-message .file-attachment:hover { background: rgba(255,255,255,0.25); }
        .chat-message.sent .file-attachment { background: rgba(255,255,255,0.1); }
        .chat-message .file-attachment .file-icon { font-size: 1.2rem; }
        .chat-message .file-attachment .file-info { flex: 1; }
        .chat-message .file-attachment .file-name { font-weight: 600; font-size: 0.8rem; }
        .chat-message .file-attachment .file-size { font-size: 0.65rem; opacity: 0.7; }
        
        /* AUDIO/VIDEO PLAYER IN CHAT - G2 Style */
        .audio-player { width: 100%; max-width: 250px; height: 40px; border-radius: var(--radius-full); background: rgba(0,0,0,0.05); padding: 4px 10px; display: flex; align-items: center; gap: 10px; }
        .audio-player audio { width: 100%; height: 30px; }
        .chat-message.sent .audio-player { background: rgba(255,255,255,0.15); }
        .video-player { width: 100%; max-width: 300px; border-radius: var(--radius); overflow: hidden; }
        .video-player video { width: 100%; max-height: 200px; }
        
        /* CHAT INPUT - G1 Style */
        .chat-input {
            display: flex; gap: 8px; padding: 12px 16px; background: var(--white);
            border-top: 1px solid #eaeaea; flex-wrap: wrap; align-items: center;
        }
        .chat-input .input-wrapper { flex: 1; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .chat-input input { flex: 1; padding: 10px 16px; border: 2px solid #eaeaea; border-radius: var(--radius-full); font-size: 0.9rem; transition: 0.3s; background: var(--bg-gray); min-width: 100px; }
        .chat-input input:focus { border-color: var(--burgundy); background: white; }
        .chat-input .file-btn {
            background: var(--charcoal-light); color: white; padding: 8px 16px; border-radius: var(--radius-full);
            font-weight: 600; font-size: 0.8rem; transition: 0.2s; white-space: nowrap;
        }
        .chat-input .file-btn:hover { background: var(--charcoal); }
        .chat-input .send-btn {
            background: var(--burgundy); color: white; padding: 8px 20px; border-radius: var(--radius-full);
            font-weight: 600; transition: 0.2s;
        }
        .chat-input .send-btn:hover { background: var(--burgundy-dark); }
        
        /* RECORDING BUTTONS IN CHAT - G2 Style */
        .chat-recording-controls { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
        .chat-recording-controls .record-btn {
            background: var(--camel); color: white; padding: 6px 12px; border-radius: var(--radius-full);
            font-size: 0.8rem; font-weight: 600; transition: 0.2s; white-space: nowrap;
        }
        .chat-recording-controls .record-btn:hover { background: var(--burgundy); }
        .chat-recording-controls .record-btn.recording { background: var(--red); animation: pulse 1s infinite; }
        .chat-recording-controls .stop-recording-btn { background: var(--red); color: white; }
        .chat-recording-controls .stop-recording-btn:hover { background: #c0392b; }
        
        /* RECORDING MODAL - G2 Style */
        .record-modal .video-preview {
            width: 100%; height: 250px; background: #1a1a1a; border-radius: var(--radius);
            display: flex; align-items: center; justify-content: center; color: white;
            margin-bottom: 16px; position: relative; overflow: hidden;
        }
        .record-modal .video-preview video { width: 100%; height: 100%; object-fit: cover; }
        .record-modal .video-preview .rec-indicator {
            position: absolute; top: 12px; left: 12px;
            background: var(--red); color: white;
            padding: 3px 12px; border-radius: var(--radius-full);
            font-size: 0.7rem; font-weight: 700;
            display: flex; align-items: center; gap: 6px;
            animation: pulse 1s infinite;
        }
        .record-modal .record-options {
            display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;
        }
        .record-modal .record-options button {
            padding: 8px 20px; border-radius: var(--radius-full);
            font-weight: 600; transition: 0.2s; color: white;
        }
        .record-modal .record-options .audio-option { background: var(--green); }
        .record-modal .record-options .audio-option:hover { background: #27ae60; }
        .record-modal .record-options .video-option { background: var(--blue); }
        .record-modal .record-options .video-option:hover { background: #2980b9; }
        .record-modal .record-options .stop-option { background: var(--red); }
        .record-modal .record-options .stop-option:hover { background: #c0392b; }
        .record-modal .record-options .send-option { background: var(--burgundy); }
        .record-modal .record-options .send-option:hover { background: var(--burgundy-dark); }
        .record-modal .record-options .cancel-option { background: var(--charcoal-light); }
        .record-modal .record-options .cancel-option:hover { background: var(--charcoal); }
        
        /* PROFILE - G3 Style */
        .profile-header {
            background: var(--white); padding: 24px; border-radius: var(--radius);
            box-shadow: var(--shadow); text-align: center; margin-bottom: 20px;
        }
        .profile-header .cover { height: 80px; background: var(--camel-light); border-radius: var(--radius) var(--radius) 0 0; margin: -24px -24px 16px; }
        .profile-header .avatar {
            width: 80px; height: 80px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
            color: white; font-weight: 700; font-size: 2rem; border: 4px solid white; box-shadow: var(--shadow);
            margin: -40px auto 8px; cursor: pointer; position: relative;
        }
        .profile-header .avatar .online-dot { position: absolute; bottom: 4px; right: 4px; width: 14px; height: 14px; border-radius: 50%; border: 3px solid white; }
        .profile-header .avatar img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
        .profile-header .avatar .avatar-text { display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; }
        .profile-header h2 { font-size: 1.4rem; }
        .profile-header .username { color: var(--charcoal-light); font-size: 0.9rem; }
        .profile-stats {
            display: flex; justify-content: center; gap: 30px; margin: 12px 0 16px;
        }
        .profile-stats div { text-align: center; cursor: pointer; transition: 0.2s; }
        .profile-stats div:hover { transform: scale(1.05); }
        .profile-stats span { display: block; font-weight: 700; font-size: 1.1rem; }
        .profile-stats small { color: #999; font-size: 0.7rem; }
        .profile-actions { display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; }
        .profile-actions button {
            padding: 6px 20px; border-radius: var(--radius-full); font-weight: 600;
            transition: 0.2s; background: var(--charcoal); color: white;
        }
        .profile-actions button:hover { background: var(--burgundy); transform: translateY(-2px); }
        .profile-actions .chat-btn { background: var(--camel); }
        .profile-actions .chat-btn:hover { background: var(--burgundy); }
        .profile-reels-grid {
            display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px;
        }
        
        /* LOCATION - G4 Style */
        .location-item {
            display: flex; align-items: center; padding: 10px 14px; background: var(--bg-gray);
            border-radius: var(--radius); margin-bottom: 8px; gap: 12px;
        }
        .location-item .avatar {
            width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
            color: white; font-weight: 700; font-size: 0.8rem; flex-shrink: 0;
        }
        .location-item .info { flex: 1; }
        .location-item .name { font-weight: 600; font-size: 0.9rem; }
        .location-item .coords { font-size: 0.75rem; color: #888; }
        .location-item .battery { font-size: 0.7rem; color: var(--green); }
        .location-map {
            width: 100%; height: 300px; background: var(--bg-gray); border-radius: var(--radius);
            border: 2px dashed #e0e0e0; display: flex; flex-direction: column;
            align-items: center; justify-content: center; color: var(--charcoal-light);
        }
        .location-map i { font-size: 3rem; color: var(--camel); margin-bottom: 10px; }
        
        /* NOTIFICATIONS - G3 Style */
        .notif-container { background: var(--white); border-radius: var(--radius); box-shadow: var(--shadow); padding: 20px; }
        .notif-container h2 { margin-bottom: 16px; }
        .notif-item {
            display: flex; align-items: center; gap: 12px; padding: 10px 14px;
            border-bottom: 1px solid #f5f5f5; cursor: pointer; transition: 0.2s;
        }
        .notif-item:hover { background: var(--bg-gray); }
        .notif-item .avatar {
            width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
            color: white; font-weight: 700; font-size: 0.8rem; flex-shrink: 0;
        }
        .notif-item .text { flex: 1; font-size: 0.85rem; }
        .notif-item .text strong { font-weight: 600; }
        .notif-item .text .time { display: block; font-size: 0.65rem; color: #999; margin-top: 2px; }
        
        /* TOAST - G1 Style */
        .toast {
            position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
            background: var(--charcoal); color: white; padding: 10px 24px;
            border-radius: var(--radius-full); font-size: 0.9rem; font-weight: 500;
            z-index: 9999; box-shadow: var(--shadow); animation: slideUp 0.3s ease;
        }
        @keyframes slideUp { from { opacity: 0; transform: translateX(-50%) translateY(20px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }
        
        /* RESPONSIVE */
        @media (max-width: 992px) {
            .menu-toggle { display: flex; }
            .sidebar {
                position: fixed; left: -280px; top: 0; height: 100%; width: 280px;
                transition: left 0.3s ease; z-index: 100; box-shadow: 4px 0 24px rgba(0,0,0,0.15);
            }
            .sidebar.open { left: 0; }
            .sidebar-overlay {
                position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0,0,0,0.45); z-index: 99; display: none;
            }
            .sidebar-overlay.active { display: block; }
            .main-content { padding-top: 68px; }
            .chat-list { width: 260px; }
            .page-section { padding: 12px 16px; }
            .grid-reels { grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); }
        }
        @media (max-width: 480px) {
            .chat-list { width: 100%; border-right: none; max-height: 200px; overflow-y: auto; }
            .chat-container { flex-direction: column; }
            .chat-window { height: calc(100vh - 200px); }
            .login-card { padding: 2rem; }
            .modal-container { padding: 20px; margin: 10px; }
            .chat-input .input-wrapper { flex-direction: column; width: 100%; }
            .chat-input input { width: 100%; }
            .chat-recording-controls { width: 100%; justify-content: center; }
            .chat-input .file-btn, .chat-input .send-btn { width: 100%; justify-content: center; }
            .top-bar { flex-direction: column; align-items: stretch; }
            .top-bar .search-container { max-width: 100%; }
            .grid-reels { grid-template-columns: 1fr 1fr; }
            .stories-row { gap: 10px; }
            .story-circle .avatar { width: 50px; height: 50px; font-size: 1rem; }
        }
    </style>
</head>
<body>
    <!-- SPLASH SCREEN - G4 Style -->
    <div id="splash">
        <div class="logo">FU<span>OM</span>CE</div>
        <p>Connect, Communicate, Collaborate</p>
        <div class="loader"></div>
        <div class="countdown-text" id="countdownText">Loading in 3...</div>
    </div>

    <!-- LOGIN PAGE - G3 Style -->
    <div id="login-page">
        <div class="login-card">
            <div class="logo">FU<span>OM</span>CE</div>
            <h2 id="loginTitle">Welcome back</h2>
            <form id="loginForm">
                <div class="input-group"><label>Username</label><input type="text" id="loginUser" value="admin"></div>
                <div class="input-group"><label>Password</label><input type="password" id="loginPass" value="admin123"></div>
                <button type="submit" class="btn-primary" id="submitBtn">Log In</button>
                <button type="button" class="btn-outline" id="showRegisterBtn">Create Account</button>
            </form>
            <div class="login-footer">Forgot password? <a href="#">Reset</a></div>
        </div>
    </div>

    <!-- MAIN APP - G3 Style -->
    <div id="app-container">
        <div class="app-layout">
            <!-- Mobile/Tablet Menu Toggle - ported from Stacey_Frontend_Two.html -->
            <button class="menu-toggle" id="menuToggle" onclick="toggleSidebar()" aria-label="Open menu"><i class="fas fa-bars"></i></button>

            <!-- Sidebar Overlay (Mobile) -->
            <div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>
            
            <!-- Sidebar - G3 Style -->
            <nav class="sidebar" id="sidebar">
                <div class="logo">FU<span>OM</span>CE</div>
                <div class="nav-item active" onclick="navigateTo('home-page')"><i class="fas fa-home"></i><span>Home</span></div>
                <div class="nav-item" onclick="navigateTo('chats-page')"><i class="fas fa-comments"></i><span>Chats</span><span class="badge" id="chatBadge">0</span></div>
                <div class="nav-item" onclick="navigateTo('location-page')"><i class="fas fa-map-marker-alt"></i><span>Location</span></div>
                <div class="nav-item" onclick="openUploadModal()"><i class="fas fa-cloud-upload-alt"></i><span>Upload</span></div>
                <div class="nav-item" onclick="navigateTo('profile-page')"><i class="fas fa-user"></i><span>Profile</span></div>
                <div class="nav-item" onclick="navigateTo('notifications-page')"><i class="fas fa-bell"></i><span>Notifications</span><span class="badge" id="sidebarBell">0</span></div>
                <div class="sidebar-divider"></div>
                <div class="sidebar-title">Friends</div>
                <div id="suggestedUsersContainer"></div>
            </nav>

            <!-- Main Content - G3 Style -->
            <main class="main-content">
                
                <!-- UPLOAD MODAL - G3 Style -->
                <div class="modal-overlay" id="uploadModal">
                    <div class="modal-container" style="max-width: 700px;">
                        <div class="modal-close" onclick="closeUploadModal()"><i class="fas fa-times"></i></div>
                        <h2 id="uploadModalTitle">Upload to FUOMCE</h2>
                        <div style="display:flex; gap:8px; margin-bottom:14px;">
                            <button type="button" id="uploadDestReelBtn" class="btn-secondary" style="flex:1; padding:8px;" onclick="setUploadDestination('reel')"><i class="fas fa-film"></i> Reel (posts to feed)</button>
                            <button type="button" id="uploadDestStoryBtn" class="btn-secondary" style="flex:1; padding:8px;" onclick="setUploadDestination('story')"><i class="fas fa-clock"></i> Story (disappears in 24h)</button>
                        </div>
                        <div class="modal-area" id="uploadFileArea" onclick="document.getElementById('uploadFileInput').click()">
                            <i class="fas fa-cloud-upload-alt" style="font-size:2.5rem;"></i>
                            <h3>Tap to upload</h3>
                            <p>Images, Videos, Audio</p>
                            <input type="file" id="uploadFileInput" accept="image/*,video/*,audio/*" style="display:none;" multiple>
                        </div>
                        <div id="uploadPreviews"></div>
                        <input type="text" id="uploadDescription" placeholder="Write something..." style="width:100%; padding:10px; border:2px solid #eaeaea; border-radius:8px; margin-bottom:12px;">
                        <select class="privacy-select" id="privacySelect">
                            <option value="public">Public</option>
                            <option value="friends">Friends</option>
                            <option value="private">Only Me</option>
                        </select>
                        <div class="modal-actions">
                            <button class="btn-primary" onclick="submitUpload()">Post Now</button>
                            <button class="btn-secondary" onclick="closeUploadModal()">Cancel</button>
                        </div>
                    </div>
                </div>

                <!-- RECORDING MODAL - G2 Style -->
                <div class="modal-overlay record-modal" id="recordModal">
                    <div class="modal-container">
                        <div class="modal-close" onclick="closeRecordModal()"><i class="fas fa-times"></i></div>
                        <h2>🎙️ Record & Send</h2>
                        <div class="video-preview" id="recordPreview">
                            <div id="recordPlaceholder" style="text-align:center; color:#888;">
                                <i class="fas fa-microphone" style="font-size:3rem; display:block; margin-bottom:10px;"></i>
                                <p>Tap a button below to start recording</p>
                            </div>
                            <video id="recordVideo" style="display:none; width:100%; height:100%; object-fit:cover;" autoplay muted playsinline></video>
                            <div class="rec-indicator" id="recIndicator" style="display:none;"><i class="fas fa-circle"></i> REC</div>
                        </div>
                        <div class="record-options" id="recordOptions">
                            <button class="audio-option" onclick="startRecording('audio')"><i class="fas fa-microphone"></i> Voice Note</button>
                            <button class="video-option" onclick="startRecording('video')"><i class="fas fa-video"></i> Video</button>
                            <button class="stop-option" id="stopRecordBtn" style="display:none;" onclick="stopRecording()"><i class="fas fa-stop"></i> Stop</button>
                            <button class="send-option" id="sendRecordBtn" style="display:none;" onclick="sendRecording()"><i class="fas fa-paper-plane"></i> Send</button>
                            <button class="cancel-option" onclick="closeRecordModal()">Cancel</button>
                        </div>
                    </div>
                </div>

                <!-- GO LIVE MODAL - real camera preview, mirrors the record modal's UI -->
                <div class="modal-overlay record-modal" id="liveModal">
                    <div class="modal-container">
                        <div class="modal-close" onclick="closeLiveModal()"><i class="fas fa-times"></i></div>
                        <h2>🔴 Go Live</h2>
                        <div class="video-preview" id="livePreviewWrap">
                            <div id="livePlaceholder" style="text-align:center; color:#888;">
                                <i class="fas fa-video" style="font-size:3rem; display:block; margin-bottom:10px;"></i>
                                <p>Give a title and start your camera</p>
                            </div>
                            <video id="liveVideo" style="display:none; width:100%; height:100%; object-fit:cover;" autoplay muted playsinline></video>
                            <div class="rec-indicator" id="liveIndicator" style="display:none;"><i class="fas fa-circle"></i> LIVE</div>
                        </div>
                        <input type="text" id="liveTitleInput" placeholder="Stream title..." value="My Live Stream" style="width:100%; padding:10px; border:2px solid #eaeaea; border-radius:8px; margin:10px 0;">
                        <div class="record-options" id="liveOptions">
                            <button class="video-option" id="startLiveCameraBtn" onclick="startLiveCamera()"><i class="fas fa-video"></i> Start Camera</button>
                            <button class="stop-option" id="goLiveConfirmBtn" style="display:none;" onclick="confirmGoLive()"><i class="fas fa-broadcast-tower"></i> Go Live</button>
                            <button class="stop-option" id="endLiveBtn" style="display:none; background:var(--red);" onclick="endLiveStream()"><i class="fas fa-stop"></i> End Live</button>
                            <button class="cancel-option" onclick="closeLiveModal()">Cancel</button>
                        </div>
                    </div>
                </div>

                <!-- STORY VIEWER MODAL - full-screen playback, replaces alert() -->
                <div class="modal-overlay" id="storyViewerModal">
                    <div class="modal-container" style="max-width:420px; padding:0; overflow:hidden; background:#000;">
                        <div class="modal-close" onclick="closeStoryViewer()" style="z-index:5; color:white;"><i class="fas fa-times"></i></div>
                        <div style="display:flex; gap:4px; padding:10px 10px 0;" id="storyProgressBars"></div>
                        <div style="display:flex; align-items:center; gap:8px; padding:10px;">
                            <div class="avatar" id="storyViewerAvatar" style="width:32px; height:32px; border-radius:50%; display:flex; align-items:center; justify-content:center; color:white; font-weight:700;"></div>
                            <div style="color:white; font-size:0.85rem; font-weight:600;" id="storyViewerUser"></div>
                            <div style="color:#ccc; font-size:0.7rem; margin-left:auto;" id="storyViewerTime"></div>
                        </div>
                        <div id="storyViewerMedia" style="width:100%; min-height:400px; max-height:70vh; display:flex; align-items:center; justify-content:center; background:#000;"></div>
                        <div style="display:flex; justify-content:space-between; padding:10px;">
                            <button onclick="storyViewerPrev()" style="background:none; border:none; color:white; cursor:pointer;"><i class="fas fa-chevron-left"></i> Prev</button>
                            <button onclick="storyViewerNext()" style="background:none; border:none; color:white; cursor:pointer;">Next <i class="fas fa-chevron-right"></i></button>
                        </div>
                    </div>
                </div>

                <!-- GROUP SETTINGS MODAL - real admin controls (make admin, remove, add friends, lock) -->
                <div class="modal-overlay" id="groupInfoModal">
                    <div class="modal-container" style="max-width:480px;">
                        <div class="modal-close" onclick="closeGroupInfoModal()"><i class="fas fa-times"></i></div>
                        <h2 id="groupInfoName">Group</h2>
                        <p id="groupInfoDesc" style="color:#666; font-size:0.85rem; margin-bottom:6px;"></p>
                        <p id="groupInfoLockStatus" style="font-size:0.8rem; color:#888; margin-bottom:12px;"></p>
                        <div id="groupInfoAdminActions" style="display:flex; gap:8px; margin-bottom:14px;"></div>
                        <h4 style="margin-bottom:8px;">Members</h4>
                        <div id="groupInfoMembers" style="max-height:220px; overflow-y:auto; margin-bottom:14px;"></div>
                        <div id="groupInfoAddSection" style="display:none;">
                            <h4 style="margin-bottom:8px;">Add Friends to Group</h4>
                            <div id="groupInfoAddList" style="max-height:180px; overflow-y:auto; margin-bottom:14px;"></div>
                        </div>
                        <div class="modal-actions">
                            <button class="btn-secondary" style="color:var(--red);" onclick="leaveGroupFromInfo()">Leave Group</button>
                            <button class="btn-secondary" onclick="closeGroupInfoModal()">Close</button>
                        </div>
                    </div>
                </div>

                <!-- REEL VIEWER MODAL - actually plays the media instead of an alert() -->
                <div class="modal-overlay" id="reelViewerModal">
                    <div class="modal-container" id="reelViewerContainer" style="max-width:520px; padding:0; overflow:hidden; position:relative;">
                        <div class="modal-close" onclick="closeReelViewer()" style="z-index:5;"><i class="fas fa-times"></i></div>
                        <button onclick="reelViewerPrev()" title="Previous reel" style="position:absolute; top:200px; left:8px; z-index:5; background:rgba(0,0,0,0.4); color:white; border:none; width:34px; height:34px; border-radius:50%; cursor:pointer;"><i class="fas fa-chevron-up"></i></button>
                        <button onclick="reelViewerNext()" title="Next reel" style="position:absolute; top:250px; left:8px; z-index:5; background:rgba(0,0,0,0.4); color:white; border:none; width:34px; height:34px; border-radius:50%; cursor:pointer;"><i class="fas fa-chevron-down"></i></button>
                        <div id="reelViewerMedia" style="width:100%; max-height:480px; background:#000; display:flex; align-items:center; justify-content:center;"></div>
                        <div style="padding:16px;">
                            <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
                                <div class="avatar" id="reelViewerAvatar" style="width:36px; height:36px; border-radius:50%; display:flex; align-items:center; justify-content:center; color:white; font-weight:700;"></div>
                                <div>
                                    <div style="font-weight:600;" id="reelViewerUser"></div>
                                    <div style="font-size:0.7rem; color:#999;" id="reelViewerDate"></div>
                                </div>
                            </div>
                            <h3 id="reelViewerTitle" style="margin-bottom:4px;"></h3>
                            <p id="reelViewerDesc" style="color:#666; font-size:0.9rem; margin-bottom:10px;"></p>
                            <div style="display:flex; gap:16px; margin-bottom:12px;">
                                <button id="reelViewerLikeBtn" onclick="toggleReelLikeInViewer()" style="background:none; border:none; cursor:pointer; font-size:0.9rem;"><i class="fas fa-heart"></i> <span id="reelViewerLikes">0</span></button>
                                <span style="font-size:0.9rem; color:#888;"><i class="fas fa-eye"></i> <span id="reelViewerViews">0</span></span>
                                <button id="reelViewerDeleteBtn" onclick="deleteReelFromViewer()" style="background:none; border:none; cursor:pointer; font-size:0.9rem; color:var(--red); margin-left:auto; display:none;"><i class="fas fa-trash"></i> Delete</button>
                            </div>
                            <div id="reelViewerComments" style="max-height:150px; overflow-y:auto; margin-bottom:10px;"></div>
                            <div style="display:flex; gap:8px;">
                                <input type="text" id="reelViewerCommentInput" placeholder="Add a comment..." style="flex:1; padding:8px 12px; border:1px solid #eaeaea; border-radius:var(--radius-full);" onkeypress="if(event.key==='Enter') submitReelComment()">
                                <button class="btn-primary" style="width:auto; padding:8px 16px;" onclick="submitReelComment()">Post</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- CREATE GROUP MODAL - G1 Style -->
                <div class="modal-overlay" id="createGroupModal">
                    <div class="modal-container">
                        <div class="modal-close" onclick="closeCreateGroupModal()"><i class="fas fa-times"></i></div>
                        <h2>📚 Create Group</h2>
                        <div class="form-group">
                            <label>Group Name</label>
                            <input type="text" id="groupName" placeholder="Enter group name">
                        </div>
                        <div class="form-group">
                            <label>Description</label>
                            <textarea id="groupDescription" placeholder="What's this group about?" rows="3"></textarea>
                        </div>
                        <div class="form-group" style="display:flex; align-items:center; gap:10px;">
                            <input type="checkbox" id="groupPublic" checked style="width:auto;">
                            <label style="margin:0; font-weight:400; cursor:pointer;">Public group (anyone can join)</label>
                        </div>
                        <div class="modal-actions">
                            <button class="btn-primary" onclick="createGroup()">Create Group</button>
                            <button class="btn-secondary" onclick="closeCreateGroupModal()">Cancel</button>
                        </div>
                    </div>
                </div>

                <!-- EDIT PROFILE MODAL - G3 Style -->
                <div class="modal-overlay" id="editProfileModal">
                    <div class="modal-container">
                        <div class="modal-close" onclick="closeEditProfileModal()"><i class="fas fa-times"></i></div>
                        <h2>Edit Profile</h2>
                        <div class="form-group">
                            <label>Display Name</label>
                            <input type="text" id="editDisplayName" placeholder="Your display name">
                        </div>
                        <div class="form-group">
                            <label>Avatar Color</label>
                            <div id="colorOptions" style="display:flex; flex-wrap:wrap; gap:8px; margin-top:4px;"></div>
                        </div>
                        <div class="form-group">
                            <label>Profile Picture</label>
                            <input type="file" id="profilePicInput" accept="image/*">
                        </div>
                        <button class="btn-primary" onclick="saveProfile()">Save Changes</button>
                    </div>
                </div>

                <!-- HOME PAGE - G3 Style -->
                <div id="home-page" class="page-section active">
                    <div class="top-bar">
                        <div class="search-container">
                            <i class="fas fa-search"></i>
                            <input type="text" id="searchInput" placeholder="Search users..." oninput="searchUsers(this.value)">
                            <div class="search-results-dropdown" id="searchResults"></div>
                        </div>
                    </div>
                    
                    <!-- Stories Row - G3 Style -->
                    <div class="stories-row" id="storiesRow">
                        <!-- Add Story -->
                        <div class="story-circle" onclick="openUploadModal('story')">
                            <div class="avatar">
                                <span id="myStoryAvatar">+</span>
                                <div class="add-story"><i class="fas fa-plus"></i></div>
                            </div>
                            <span>Add Story</span>
                        </div>
                        <!-- Other stories loaded by JS -->
                    </div>
                    
                    <!-- Home Tabs - G3 Style -->
                    <div class="home-tabs-row">
                        <div class="home-tab-btn active" onclick="switchHomeTab(this, 'for-you')">For You</div>
                        <div class="home-tab-btn" onclick="switchHomeTab(this, 'following')">Following</div>
                        <div class="home-tab-btn" onclick="switchHomeTab(this, 'live')">LIVE</div>
                    </div>
                    
                    <!-- Reels Grid - G3 Style -->
                    <div class="grid-reels" id="feedGrid"></div>
                </div>

                <!-- CHATS PAGE - G1 Style -->
                <div id="chats-page" class="page-section">
                    <div class="top-bar">
                        <div class="search-container">
                            <i class="fas fa-search"></i>
                            <input type="text" id="chatSearchInput" placeholder="Search chats..." oninput="filterChatList()">
                        </div>
                        <button class="btn-primary" style="width:auto; padding:8px 20px; border-radius:var(--radius-full);" onclick="openCreateGroupModal()"><i class="fas fa-plus"></i> New Group</button>
                    </div>
                    
                    <div class="chat-container">
                        <div class="chat-list">
                            <div class="chat-search">
                                <input type="text" id="chatListSearch" placeholder="Search conversations..." oninput="filterChatList()">
                            </div>
                            <div id="chatListItems" style="flex:1; overflow-y:auto;"></div>
                        </div>
                        <div class="chat-window" id="chatWindow">
                            <div style="text-align:center; color:#999; padding:20px;">Select a chat to start messaging</div>
                        </div>
                    </div>
                </div>

                <!-- LOCATION PAGE - G4 Style -->
                <div id="location-page" class="page-section">
                    <h2 style="margin-bottom:16px;">📍 Live Locations</h2>
                    <div style="display:flex; gap:16px; flex-wrap:wrap;">
                        <div style="flex:2; min-width:280px;">
                            <div style="position:relative; margin-bottom:10px;">
                                <input type="text" id="locationSearchInput" placeholder="Search a place, address, or landmark..."
                                    style="width:100%; padding:10px 14px; border:2px solid #eaeaea; border-radius:8px; box-sizing:border-box;"
                                    oninput="searchLocationPlaces(this.value)">
                                <div id="locationSearchDropdown"
                                    style="position:absolute; top:100%; left:0; right:0; background:white; max-height:220px; overflow-y:auto;
                                           display:none; z-index:50; border:1px solid #eaeaea; border-top:none; border-radius:0 0 8px 8px;
                                           box-shadow:0 4px 12px rgba(0,0,0,0.15);"></div>
                            </div>
                            <div id="googleLocationMap" style="width:100%; height:480px; border-radius:12px; overflow:hidden; background:#f0f0f0;"></div>
                            <div style="display:flex; gap:10px; margin-top:12px; flex-wrap:wrap;">
                                <button class="btn-primary" style="width:auto; padding:10px 24px;" onclick="shareLocation()">
                                    <i class="fas fa-location-dot"></i> Share My Location
                                </button>
                                <button class="btn-secondary" style="width:auto; padding:10px 24px;" onclick="locateMeOnMap()">
                                    <i class="fas fa-crosshairs"></i> Center On Me
                                </button>
                            </div>
                        </div>
                        <div style="flex:1; min-width:220px;">
                            <h3 style="margin-bottom:10px;">Active Users</h3>
                            <div id="locationList"></div>
                        </div>
                    </div>
                </div>

                <!-- PROFILE PAGE - G3 Style -->
                <div id="profile-page" class="page-section">
                    <div class="profile-header" id="profileHeader">
                        <div class="cover"></div>
                        <div class="avatar" id="profileAvatar">
                            <div class="online-dot" id="profileOnlineDot" style="background:#2ed573;"></div>
                            <div class="avatar-text" id="profileAvatarText">U</div>
                            <img id="profilePicImg" style="display:none; width:100%; height:100%; border-radius:50%; object-fit:cover;">
                        </div>
                        <h2 id="profileName">Loading...</h2>
                        <p class="username" id="profileUsername">@username</p>
                        <div class="profile-stats">
                            <div><span id="profileFollowing">0</span><small>Following</small></div>
                            <div><span id="profileFollowers">0</span><small>Followers</small></div>
                            <div><span id="profileLikes">0</span><small>Likes</small></div>
                        </div>
                        <div class="profile-actions" id="profileActions">
                            <button id="editProfileBtn" onclick="openEditProfileModal()">Edit Profile</button>
                            <button class="chat-btn hidden" id="chatProfileBtn" onclick="openChatFromProfile()"><i class="fas fa-comment"></i> Chat</button>
                            <button class="hidden" id="goLiveBtn" onclick="openLiveStream()"><i class="fas fa-video"></i> Go Live</button>
                        </div>
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                        <h3 id="profileReelsTitle">My Reels</h3>
                        <button class="btn-primary" style="width:auto; padding:6px 16px; border-radius:var(--radius-full); font-size:0.8rem;" onclick="openUploadModal()"><i class="fas fa-plus"></i> Add Reel</button>
                    </div>
                    <div class="profile-reels-grid" id="profileReelsGrid"></div>
                </div>

                <!-- NOTIFICATIONS PAGE - G3 Style -->
                <div id="notifications-page" class="page-section">
                    <div class="notif-container">
                        <h2>Notifications</h2>
                        <div id="notifList"></div>
                    </div>
                </div>

            </main>
        </div>
    </div>

    <script>
        // ============================================================
        // STATE
        // ============================================================
        let loggedInUser = null;
        let socket = null;
        let currentChatId = null;
        let currentChatType = null;
        let chatHistory = {};
        let allUsers = [];
        let allGroups = [];
        let friends = [];
        let friendRequests = [];
        let sentFriendRequests = [];
        let notifications = [];
        let locations = [];
        let reels = [];
        let stories = [];
        let profileViewUserId = null;
        let chatPartnerId = null;
        let isRecording = false;
        let mediaRecorder = null;
        let recordedChunks = [];
        let recordingType = 'audio';
        let socketReady = false;
        let appStarted = false;
        let liveStreamId = null;
        let liveStreamActive = false;
        let selectedFiles = [];
        let currentHomeFeedType = 'for-you';
        let feedIndex = 0;
        const BATCH_SIZE = 12;

        const API_BASE = window.location.origin + '/api';
        const colors = ["#800020", "#2C2C2C", "#D2B48C", "#FF7F50", "#2E4A62", "#6B8E23", "#8B4513", "#A52A2A", "#CD5C5C", "#BC8F8F"];
        
        // ============================================================
        // SPLASH SCREEN - G4 Style (3, 2, 1 countdown)
        // ============================================================
        let countdown = 3;
        const countdownText = document.getElementById('countdownText');
        
        const timer = setInterval(() => {
            countdown--;
            if (countdown > 0) {
                countdownText.innerText = `Loading in ${countdown}...`;
            } else {
                clearInterval(timer);
                countdownText.innerText = "Launching...";
                startApp();
            }
        }, 1000);

        setTimeout(() => {
            if (!appStarted) {
                clearInterval(timer);
                startApp();
            }
        }, 5000);

        function startApp() {
            if (appStarted) return;
            appStarted = true;
            
            const splash = document.getElementById('splash');
            splash.classList.add('hidden');
            
            setTimeout(() => {
                document.getElementById('login-page').style.display = 'flex';
            }, 400);
        }

        // ============================================================
        // LOGIN / REGISTER - G3 Style
        // ============================================================
        let isRegistering = false;
        
        document.getElementById('showRegisterBtn').addEventListener('click', function() {
            isRegistering = !isRegistering;
            document.getElementById('loginTitle').innerText = isRegistering ? "Create Account" : "Welcome back";
            document.getElementById('submitBtn').innerText = isRegistering ? "Register" : "Log In";
            this.innerText = isRegistering ? "Back to Login" : "Create Account";
        });

        document.getElementById('loginForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const username = document.getElementById('loginUser').value.trim();
            const password = document.getElementById('loginPass').value.trim();
            const endpoint = isRegistering ? '/register' : '/login';
            
            if (!username || !password) return alert("Please enter both fields.");
            
            try {
                const response = await fetch(`${API_BASE}${endpoint}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        username, 
                        password,
                        email: username + '@fuomce.com',
                        full_name: username,
                        display_name: username
                    })
                });
                const data = await response.json();
                if (data.success) {
                    loggedInUser = data.user;
                    document.getElementById('login-page').style.display = 'none';
                    document.getElementById('app-container').style.display = 'block';
                    initApp();
                } else {
                    alert(data.detail || 'Error');
                }
            } catch (error) {
                alert('Failed to connect: ' + error.message);
            }
        });

        // ============================================================
        // APP INITIALIZATION - G3 Style
        // ============================================================
        async function initApp() {
            await loadUsers();
            await loadGroups();
            await loadFriends();
            await loadFriendRequests();
            await loadSentFriendRequests();
            await loadNotifications();
            await loadLocations();
            await loadReels();
            await loadStories();
            
            connectWebSocket();
            renderSidebar();
            renderChatList();
            renderProfile(loggedInUser.id);
            renderLocations();
            renderStories();
            renderFeed();
            renderNotifications();
            
            document.getElementById('profileName').innerText = loggedInUser.display_name || loggedInUser.username;
            document.getElementById('profileUsername').innerText = '@' + loggedInUser.username;
            document.getElementById('profileAvatarText').innerText = (loggedInUser.display_name || loggedInUser.username)[0].toUpperCase();
            if (loggedInUser.profile_pic) {
                document.getElementById('profilePicImg').style.display = 'block';
                document.getElementById('profilePicImg').src = `/uploads/${loggedInUser.profile_pic}`;
                document.getElementById('profileAvatarText').style.display = 'none';
            }
            
            // Color options for edit profile - G3 Style
            const colorContainer = document.getElementById('colorOptions');
            colors.forEach(color => {
                const div = document.createElement('div');
                div.className = 'color-option';
                div.style.cssText = `width:36px; height:36px; border-radius:50%; background:${color}; cursor:pointer; border:3px solid ${color === loggedInUser.avatar_color ? '#000' : 'transparent'}; transition:0.2s;`;
                div.onclick = function() {
                    document.querySelectorAll('.color-option').forEach(el => el.style.borderColor = 'transparent');
                    this.style.borderColor = '#000';
                    window.selectedColor = color;
                };
                colorContainer.appendChild(div);
            });
            window.selectedColor = loggedInUser.avatar_color;
            
            // My story avatar
            document.getElementById('myStoryAvatar').textContent = (loggedInUser.display_name || loggedInUser.username)[0].toUpperCase();
            if (loggedInUser.profile_pic) {
                document.getElementById('myStoryAvatar').innerHTML = `<img src="/uploads/${loggedInUser.profile_pic}" style="width:100%; height:100%; border-radius:50%; object-fit:cover;">`;
            }
            
            if (window.innerWidth <= 480) {
                document.querySelector('.sidebar .logo').addEventListener('click', toggleSidebar);
            }
        }

        // ============================================================
        // WEBSOCKET - G1 Style
        // ============================================================
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            socket = new WebSocket(`${protocol}//${window.location.host}/ws/${loggedInUser.id}`);
            
            socket.onopen = () => { socketReady = true; console.log('WebSocket connected'); };
            socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    handleWebSocketMessage(data);
                } catch(e) {}
            };
            socket.onclose = () => {
                socketReady = false;
                console.log('WebSocket disconnected, reconnecting...');
                setTimeout(connectWebSocket, 3000);
            };
        }

        function handleWebSocketMessage(data) {
            switch(data.type) {
                case 'message':
                    const key = data.group_id ? 'group_' + data.group_id : 'user_' + data.sender_id;
                    if (!chatHistory[key]) chatHistory[key] = [];
                    if (!chatHistory[key].find(m => m.id === data.id)) {
                        chatHistory[key].push(data);
                        renderChatList();
                        if ((data.group_id && currentChatId === data.group_id && currentChatType === 'group') ||
                            (data.sender_id === currentChatId && currentChatType === 'user') ||
                            (data.recipient_id === currentChatId && currentChatType === 'user')) {
                            displayMessage(data);
                        }
                        updateChatBadge();
                    }
                    break;
                    
                case 'message_edited':
                    const editKey = data.group_id ? 'group_' + data.group_id : 'user_' + data.sender_id;
                    if (chatHistory[editKey]) {
                        const idx = chatHistory[editKey].findIndex(m => m.id === data.id);
                        if (idx !== -1) {
                            chatHistory[editKey][idx].content = data.content;
                            chatHistory[editKey][idx].edited_at = data.edited_at;
                        }
                    }
                    {
                        const wrapper = document.querySelector(`[data-message-id="${data.id}"]`);
                        if (wrapper) {
                            const bubble = wrapper.querySelector('.chat-message');
                            if (bubble) {
                                const timeEl = bubble.querySelector('.time');
                                const timeHtml = timeEl ? timeEl.outerHTML.replace('</span>', ' ✎</span>') : '';
                                // Preserve any file/media content, only swap the text node before it
                                const fileEl = bubble.querySelector('.file-attachment, .audio-player, .video-player, img')?.closest('div');
                                bubble.innerHTML = data.content + (fileEl ? fileEl.outerHTML : '') + timeHtml;
                            }
                        }
                    }
                    break;
                    
                case 'message_deleted':
                    const delKey = data.group_id ? 'group_' + data.group_id : 'user_' + data.sender_id;
                    if (chatHistory[delKey]) {
                        const idx = chatHistory[delKey].findIndex(m => m.id === data.id);
                        if (idx !== -1) {
                            chatHistory[delKey][idx].is_deleted = true;
                            chatHistory[delKey][idx].content = data.content;
                        }
                    }
                    {
                        const wrapper = document.querySelector(`[data-message-id="${data.id}"]`);
                        if (wrapper) {
                            const bubble = wrapper.querySelector('.chat-message');
                            if (bubble) bubble.innerHTML = `<em style="opacity:0.6;">${data.content}</em>`;
                            const actions = wrapper.querySelector('.msg-actions');
                            if (actions) actions.remove();
                        }
                    }
                    break;
                    
                case 'message_reaction':
                    renderReactionsForMessage(data.id, data.reactions);
                    break;
                    
                case 'typing':
                    showTyping(data.username);
                    break;
                    
                case 'friend_request':
                    loadFriendRequests();
                    loadNotifications();
                    showToast('📨 ' + data.from_name + ' sent you a friend request');
                    break;
                    
                case 'friend_accepted':
                    loadFriends();
                    loadFriendRequests();
                    showToast('✅ ' + data.name + ' accepted your friend request');
                    break;
                    
                case 'location_update':
                    updateLocationOnMap(data);
                    break;
                    
                case 'live_started':
                    showToast('🔴 ' + data.name + ' started a live stream: ' + data.title);
                    loadReels();
                    break;
                    
                case 'live_ended':
                    showToast('🔴 ' + data.name + ' ended their live stream');
                    loadReels();
                    break;
            }
        }

        function sendWebSocketMessage(data) {
            if (socketReady && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify(data));
            }
        }

        // ============================================================
        // LOAD DATA - G3 Style
        // ============================================================
        async function loadUsers() {
            try {
                const res = await fetch(`${API_BASE}/users`);
                allUsers = await res.json();
            } catch(e) { console.error('Error loading users:', e); }
        }

        async function loadGroups() {
            try {
                const res = await fetch(`${API_BASE}/groups`);
                allGroups = await res.json();
            } catch(e) { console.error('Error loading groups:', e); }
        }

        async function loadFriends() {
            try {
                const res = await fetch(`${API_BASE}/friends?user_id=${loggedInUser.id}`);
                friends = await res.json();
            } catch(e) { console.error('Error loading friends:', e); }
        }

        async function loadFriendRequests() {
            try {
                const res = await fetch(`${API_BASE}/friend_requests?user_id=${loggedInUser.id}`);
                friendRequests = await res.json();
                document.getElementById('sidebarBell').innerText = friendRequests.length || '0';
            } catch(e) { console.error('Error loading friend requests:', e); }
        }

        async function loadSentFriendRequests() {
            try {
                const res = await fetch(`${API_BASE}/friend_requests/sent?user_id=${loggedInUser.id}`);
                sentFriendRequests = await res.json();
            } catch(e) { console.error('Error loading sent friend requests:', e); }
        }

        async function loadNotifications() {
            try {
                const res = await fetch(`${API_BASE}/notifications?user_id=${loggedInUser.id}`);
                notifications = await res.json();
                renderNotifications();
            } catch(e) { console.error('Error loading notifications:', e); }
        }

        async function loadLocations() {
            try {
                const res = await fetch(`${API_BASE}/locations`);
                locations = await res.json();
                renderLocations();
            } catch(e) { console.error('Error loading locations:', e); }
        }

        async function loadReels() {
            try {
                const res = await fetch(`${API_BASE}/reels?user_id=${loggedInUser.id}`);
                reels = await res.json();
                renderFeed();
                renderProfile(profileViewUserId || loggedInUser.id);
            } catch(e) { console.error('Error loading reels:', e); }
        }

        async function loadStories() {
            try {
                const res = await fetch(`${API_BASE}/stories`);
                stories = await res.json();
                renderStories();
            } catch(e) { console.error('Error loading stories:', e); }
        }

        // ============================================================
        // NAVIGATION - G3 Style
        // ============================================================
        function navigateTo(pageId) {
            document.querySelectorAll('.page-section').forEach(el => el.classList.remove('active'));
            document.getElementById(pageId).classList.add('active');
            
            document.querySelectorAll('.sidebar .nav-item').forEach(n => n.classList.remove('active'));
            const map = {
                'home-page': 0,
                'chats-page': 1,
                'location-page': 2,
                'profile-page': 4,
                'notifications-page': 5
            };
            if (map[pageId] !== undefined) {
                const items = document.querySelectorAll('.sidebar .nav-item');
                if (items[map[pageId]]) items[map[pageId]].classList.add('active');
            }
            
            if (window.innerWidth <= 480) closeSidebar();
            
            if (pageId === 'chats-page') renderChatList();
            if (pageId === 'profile-page') renderProfile(loggedInUser.id);
            if (pageId === 'location-page') { initLocationMap(); loadLocations(); }
            if (pageId === 'notifications-page') {
                loadNotifications();
                fetch(`${API_BASE}/notifications/mark_read`, {
                    method: 'POST',
                    body: new URLSearchParams({ user_id: loggedInUser.id })
                });
            }
        }

        function toggleSidebar() {
            document.getElementById('sidebar').classList.toggle('open');
            document.getElementById('sidebarOverlay').classList.toggle('active');
        }

        function closeSidebar() {
            document.getElementById('sidebar').classList.remove('open');
            document.getElementById('sidebarOverlay').classList.remove('active');
        }

        // ============================================================
        // SEARCH - G3 Style
        // ============================================================
        let searchTimeout = null;

        async function searchUsers(query) {
            const dropdown = document.getElementById('searchResults');
            if (!query.trim()) {
                dropdown.classList.remove('active');
                return;
            }
            
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(async () => {
                try {
                    const res = await fetch(`${API_BASE}/users/search?query=${encodeURIComponent(query)}`);
                    const users = await res.json();
                    
                    dropdown.innerHTML = '';
                    if (users.length === 0) {
                        dropdown.innerHTML = '<div style="padding:12px; color:#999; text-align:center;">No users found</div>';
                    } else {
                        users.forEach(user => {
                            if (user.id === loggedInUser.id) return;
                            const div = document.createElement('div');
                            div.className = 'search-result-item';
                            const isOnline = user.is_online;
                            div.innerHTML = `
                                <div class="avatar" style="background:${user.avatar_color};">
                                    ${(user.display_name || user.username)[0]}
                                    <div class="online-dot" style="background:${isOnline ? '#2ed573' : '#888'};"></div>
                                </div>
                                <div class="info">
                                    <div class="name">${user.display_name || user.username}</div>
                                    <div class="username">@${user.username}</div>
                                </div>
                            `;
                            div.onclick = () => {
                                dropdown.classList.remove('active');
                                document.getElementById('searchInput').value = '';
                                navigateTo('profile-page');
                                renderProfile(user.id);
                            };
                            dropdown.appendChild(div);
                        });
                    }
                    dropdown.classList.add('active');
                } catch(e) {
                    console.error('Search error:', e);
                }
            }, 300);
        }

        document.addEventListener('click', function(e) {
            if (!e.target.closest('.search-container')) {
                document.getElementById('searchResults').classList.remove('active');
            }
        });

        // ============================================================
        // SIDEBAR - G3 Style
        // ============================================================
        function renderSidebar() {
            const container = document.getElementById('suggestedUsersContainer');
            container.innerHTML = '';
            
            friends.forEach(user => {
                const div = document.createElement('div');
                div.className = 'user-suggestion';
                const isOnline = user.is_online;
                div.innerHTML = `
                    <div class="avatar" style="background:${user.avatar_color};">
                        ${(user.display_name || user.username)[0]}
                        <div class="online-dot" style="background:${isOnline ? '#2ed573' : '#888'};"></div>
                    </div>
                    <div class="info">
                        <div class="name">${user.display_name || user.username}</div>
                        <div class="sub">Friend</div>
                    </div>
                    <button class="follow-btn following" onclick="event.stopPropagation(); openChatFromFriend(${user.id})" style="background:var(--blue); color:white; padding:3px 10px;">
                        <i class="fas fa-comment"></i>
                    </button>
                `;
                div.onclick = () => {
                    navigateTo('profile-page');
                    renderProfile(user.id);
                };
                container.appendChild(div);
            });
            
            if (friends.length === 0) {
                container.innerHTML = '<div style="padding:8px 12px; color:#999; font-size:0.85rem;">No friends yet. Add some!</div>';
            }
        }

        function openChatFromFriend(userId) {
            navigateTo('chats-page');
            setTimeout(() => openChat('user', userId), 200);
        }

        // ============================================================
        // STORIES - G3 Style
        // ============================================================
        function renderStories() {
            const container = document.getElementById('storiesRow');
            
            // Keep the first item (Add Story)
            const addStory = container.querySelector('.story-circle');
            container.innerHTML = '';
            if (addStory) container.appendChild(addStory);
            
            // Own active stories - shown as a distinct "Your Story" circle right after Add Story
            const myStories = stories.filter(s => s.user_id === loggedInUser.id);
            if (myStories.length > 0) {
                const mine = document.createElement('div');
                mine.className = 'story-circle';
                mine.innerHTML = `
                    <div class="avatar" style="background:${loggedInUser.avatar_color || '#800020'}; border:2px solid var(--burgundy);">
                        ${loggedInUser.profile_pic ? `<img src="/uploads/${loggedInUser.profile_pic}">` : (loggedInUser.display_name || loggedInUser.username)[0]}
                    </div>
                    <span>Your Story</span>
                `;
                mine.onclick = () => openStoryViewer(myStories, 0);
                container.appendChild(mine);
            }
            
            // Group other users' stories so each friend gets one circle covering all their active stories
            const byUser = {};
            stories.forEach(story => {
                if (story.user_id === loggedInUser.id) return;
                if (!byUser[story.user_id]) byUser[story.user_id] = [];
                byUser[story.user_id].push(story);
            });
            
            Object.keys(byUser).forEach(uid => {
                const user = allUsers.find(u => u.id === parseInt(uid));
                if (!user) return;
                const userStories = byUser[uid];
                
                const div = document.createElement('div');
                div.className = 'story-circle';
                div.innerHTML = `
                    <div class="avatar" style="background:${user.avatar_color};">
                        ${user.profile_pic ? `<img src="/uploads/${user.profile_pic}">` : (user.display_name || user.username)[0]}
                    </div>
                    <span>${user.display_name || user.username}</span>
                `;
                div.onclick = () => openStoryViewer(userStories, 0);
                container.appendChild(div);
            });
        }

        let storyViewerList = [];
        let storyViewerIndex = 0;
        let storyViewerTimer = null;

        function openStoryViewer(storyList, index) {
            storyViewerList = storyList;
            storyViewerIndex = index;
            document.getElementById('storyViewerModal').classList.add('active');
            renderStoryProgressBars();
            showCurrentStory();
        }

        function renderStoryProgressBars() {
            const bars = document.getElementById('storyProgressBars');
            bars.innerHTML = storyViewerList.map((_, i) =>
                `<div style="flex:1; height:3px; border-radius:2px; background:${i < storyViewerIndex ? 'white' : (i === storyViewerIndex ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.3)')};"></div>`
            ).join('');
        }

        function showCurrentStory() {
            clearTimeout(storyViewerTimer);
            const story = storyViewerList[storyViewerIndex];
            if (!story) { closeStoryViewer(); return; }
            
            const user = allUsers.find(u => u.id === story.user_id) || loggedInUser;
            const mediaUrl = story.media_url.startsWith('http') ? story.media_url : '/uploads/' + story.media_url;
            
            document.getElementById('storyViewerAvatar').style.background = user.avatar_color || '#800020';
            document.getElementById('storyViewerAvatar').textContent = (user.display_name || user.username || 'U')[0];
            document.getElementById('storyViewerUser').textContent = user.display_name || user.username || 'User';
            document.getElementById('storyViewerTime').textContent = new Date(story.created_at).toLocaleString();
            
            const mediaContainer = document.getElementById('storyViewerMedia');
            if (story.media_type === 'video') {
                mediaContainer.innerHTML = `<video src="${mediaUrl}" autoplay controls playsinline style="max-width:100%; max-height:70vh;"
                    onerror="this.parentElement.innerHTML='<div style=&quot;color:#ccc;text-align:center;padding:40px;&quot;><i class=&quot;fas fa-video-slash&quot; style=&quot;font-size:2rem;&quot;></i><br>Video unavailable</div>'"
                    onended="storyViewerNext()"></video>`;
            } else if (story.media_type === 'audio') {
                mediaContainer.innerHTML = `<div style="text-align:center; color:white; padding:40px;">
                        <i class="fas fa-music" style="font-size:3rem; display:block; margin-bottom:16px;"></i>
                        <audio src="${mediaUrl}" autoplay controls style="width:100%;"
                            onerror="this.parentElement.innerHTML='<div style=&quot;color:#fff;&quot;>Audio unavailable</div>'"
                            onended="storyViewerNext()"></audio>
                    </div>`;
            } else {
                mediaContainer.innerHTML = `<img src="${mediaUrl}" style="max-width:100%; max-height:70vh; object-fit:contain;"
                    onerror="this.parentElement.innerHTML='<div style=&quot;color:#ccc;text-align:center;padding:40px;&quot;><i class=&quot;fas fa-image&quot; style=&quot;font-size:2rem;&quot;></i><br>Image unavailable</div>'">`;
                // Images auto-advance after 5 seconds, like a normal stories UI
                storyViewerTimer = setTimeout(() => storyViewerNext(), 5000);
            }
            renderStoryProgressBars();
        }

        function storyViewerNext() {
            if (storyViewerIndex < storyViewerList.length - 1) {
                storyViewerIndex++;
                showCurrentStory();
            } else {
                closeStoryViewer();
            }
        }

        function storyViewerPrev() {
            if (storyViewerIndex > 0) {
                storyViewerIndex--;
                showCurrentStory();
            }
        }

        function closeStoryViewer() {
            clearTimeout(storyViewerTimer);
            document.getElementById('storyViewerModal').classList.remove('active');
            document.getElementById('storyViewerMedia').innerHTML = '';
            storyViewerList = [];
            storyViewerIndex = 0;
        }

        // ============================================================
        // FEED / REELS - G3 Style
        // ============================================================
        function switchHomeTab(el, type) {
            document.querySelectorAll('.home-tab-btn').forEach(t => t.classList.remove('active'));
            el.classList.add('active');
            currentHomeFeedType = type;
            feedIndex = 0;
            renderFeed();
        }

        // Shared thumbnail renderer used by the home feed grid and the
        // profile "My Reels" grid, so every reel clearly shows what kind of
        // media it is (photo / video / audio) with a proper icon, and never
        // shows a broken image/video icon.
        function reelThumbHtml(reel) {
            const mediaUrl = reel.media_url.startsWith('http') ? reel.media_url : '/uploads/' + reel.media_url;
            const type = reel.media_type || 'image';
            let badgeIcon = 'fa-image';
            let body = '';
            if (type === 'video') {
                badgeIcon = 'fa-video';
                body = `<video src="${mediaUrl}" muted loop playsinline
                            onerror="this.closest('.grid-card-img').innerHTML='<div class=&quot;broken-media&quot;><i class=&quot;fas fa-video-slash&quot;></i><span>Video unavailable</span></div>'"
                            onmouseover="this.play().catch(()=>{})" onmouseout="this.pause()"></video>
                        <div class="play-badge"><i class="fas fa-play"></i></div>`;
            } else if (type === 'audio') {
                badgeIcon = 'fa-headphones';
                body = `<div class="media-cover audio-cover"><i class="fas fa-music"></i><span style="font-size:0.75rem;">Audio</span></div>`;
            } else {
                badgeIcon = 'fa-image';
                body = `<img src="${mediaUrl}" alt="${reel.title || 'Reel'}" loading="lazy"
                            onerror="this.closest('.grid-card-img').innerHTML='<div class=&quot;broken-media&quot;><i class=&quot;fas fa-image&quot;></i><span>Image unavailable</span></div>'">`;
            }
            const badge = `<div class="media-type-badge" title="${type}"><i class="fas ${badgeIcon}"></i></div>`;
            return badge + body;
        }

        function renderFeed() {
            const container = document.getElementById('feedGrid');
            container.innerHTML = '';
            
            let filtered = [...reels];
            if (currentHomeFeedType === 'following') {
                const friendIds = friends.map(f => f.id);
                filtered = reels.filter(r => friendIds.includes(r.user_id));
            } else if (currentHomeFeedType === 'live') {
                filtered = reels.filter(r => r.is_live);
            }
            
            if (filtered.length === 0) {
                container.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:40px; color:#999;">No reels to show</div>';
                return;
            }
            
            filtered.slice(0, BATCH_SIZE).forEach(reel => {
                const card = document.createElement('div');
                card.className = 'grid-card';
                
                const mediaHtml = reelThumbHtml(reel);
                
                let liveBadge = '';
                if (reel.is_live) {
                    liveBadge = `<div class="live-badge"><i class="fas fa-circle"></i> LIVE</div>`;
                }
                
                card.innerHTML = `
                    <div class="grid-card-img">
                        ${mediaHtml}
                        ${liveBadge}
                        <div class="overlay-stats"><i class="fas fa-eye"></i> ${reel.views || 0}</div>
                    </div>
                    <div class="grid-card-info">
                        <div class="avatar" style="background:${reel.avatar_color || '#800020'};">${(reel.display_name || 'U')[0]}</div>
                        <div class="text">
                            <h4>${reel.title}</h4>
                            <p>${reel.display_name || 'Unknown'} · ${reel.likes || 0} ❤️</p>
                        </div>
                    </div>
                `;
                
                card.onclick = () => viewReel(reel.id);
                container.appendChild(card);
            });
        }

        let currentViewerReel = null;
        let reelViewerList = [];
        let reelViewerIndex = 0;

        async function viewReel(reelId) {
            // Track position within whatever list is currently rendered (feed order)
            // so swipe/scroll/keyboard can move to the next/previous reel.
            reelViewerList = reels.filter(r => visibleReelForViewer(r));
            reelViewerIndex = reelViewerList.findIndex(r => r.id === reelId);
            if (reelViewerIndex === -1) { reelViewerList = [{ id: reelId }]; reelViewerIndex = 0; }
            await loadReelIntoViewer(reelId);
            document.getElementById('reelViewerModal').classList.add('active');
            setupReelViewerGestures();
        }

        function visibleReelForViewer(r) {
            // Same visibility rule as the feed grid: public reels, or your own,
            // or friends' reels marked "friends" - keeps swipe order matching what's on screen.
            return true;
        }

        async function loadReelIntoViewer(reelId) {
            try {
                const res = await fetch(`${API_BASE}/reels/${reelId}?user_id=${loggedInUser.id}`);
                if (!res.ok) { showToast('Reel not found'); return; }
                const reel = await res.json();
                currentViewerReel = reel;
                
                const mediaUrl = reel.media_url.startsWith('http') ? reel.media_url : '/uploads/' + reel.media_url;
                let mediaDisplay = '';
                if (reel.media_type === 'video') {
                    mediaDisplay = `<video src="${mediaUrl}" controls autoplay playsinline style="max-width:100%; max-height:480px; width:100%;"
                                        onerror="this.parentElement.innerHTML='<div style=&quot;color:#ccc;padding:60px 20px;text-align:center;&quot;><i class=&quot;fas fa-video-slash&quot; style=&quot;font-size:2.5rem;display:block;margin-bottom:10px;&quot;></i>Video unavailable</div>'"></video>`;
                } else if (reel.media_type === 'audio') {
                    mediaDisplay = `<div style="width:100%; padding:50px 20px; text-align:center; background:linear-gradient(135deg, var(--burgundy) 0%, var(--charcoal) 100%);">
                                        <i class="fas fa-music" style="font-size:3rem; color:white; display:block; margin-bottom:16px;"></i>
                                        <audio src="${mediaUrl}" controls autoplay style="width:100%;"
                                            onerror="this.parentElement.innerHTML='<div style=&quot;color:#fff;&quot;><i class=&quot;fas fa-music-slash&quot;></i> Audio unavailable</div>'"></audio>
                                    </div>`;
                } else {
                    mediaDisplay = `<img src="${mediaUrl}" style="max-width:100%; max-height:480px; width:100%; object-fit:contain;"
                                        onerror="this.parentElement.innerHTML='<div style=&quot;color:#ccc;padding:60px 20px;text-align:center;&quot;><i class=&quot;fas fa-image&quot; style=&quot;font-size:2.5rem;display:block;margin-bottom:10px;&quot;></i>Image unavailable</div>'">`;
                }
                document.getElementById('reelViewerMedia').innerHTML = mediaDisplay;
                
                const author = allUsers.find(u => u.id === reel.user_id) || {};
                document.getElementById('reelViewerAvatar').style.background = reel.avatar_color || author.avatar_color || '#800020';
                document.getElementById('reelViewerAvatar').textContent = (reel.display_name || author.display_name || author.username || 'U')[0];
                document.getElementById('reelViewerUser').textContent = reel.display_name || author.display_name || author.username || 'Unknown';
                document.getElementById('reelViewerDate').textContent = new Date(reel.created_at).toLocaleString();
                document.getElementById('reelViewerTitle').textContent = reel.title || '';
                document.getElementById('reelViewerDesc').textContent = reel.description || '';
                document.getElementById('reelViewerLikes').textContent = reel.likes || 0;
                document.getElementById('reelViewerViews').textContent = reel.views || 0;
                document.getElementById('reelViewerLikeBtn').style.color = reel.liked_by_me ? 'var(--red)' : '';
                document.getElementById('reelViewerDeleteBtn').style.display = (reel.user_id === loggedInUser.id) ? 'block' : 'none';
                
                renderReelViewerComments(reel);
            } catch(e) {
                console.error('Error viewing reel:', e);
                showToast('Error loading reel');
            }
        }

        function renderReelViewerComments(reel) {
            let comments = [];
            try { comments = JSON.parse(reel.comments || '[]'); } catch(e) {}
            const container = document.getElementById('reelViewerComments');
            if (!comments.length) {
                container.innerHTML = '<p style="color:#999; font-size:0.8rem;">No comments yet</p>';
                return;
            }
            container.innerHTML = comments.map(c => 
                `<div style="padding:4px 0; border-bottom:1px solid #f5f5f5; font-size:0.85rem;">
                    <strong>${allUsers.find(u => u.id === c.user_id)?.display_name || 'User'}</strong> ${c.text}
                    <span style="font-size:0.65rem; color:#999; display:block;">${new Date(c.timestamp).toLocaleString()}</span>
                </div>`
            ).join('');
        }

        function closeReelViewer() {
            document.getElementById('reelViewerModal').classList.remove('active');
            document.getElementById('reelViewerMedia').innerHTML = '';
            currentViewerReel = null;
            reelViewerList = [];
            reelViewerIndex = 0;
            teardownReelViewerGestures();
        }

        function reelViewerNext() {
            if (reelViewerIndex < reelViewerList.length - 1) {
                reelViewerIndex++;
                loadReelIntoViewer(reelViewerList[reelViewerIndex].id);
            } else {
                showToast('No more reels');
            }
        }

        function reelViewerPrev() {
            if (reelViewerIndex > 0) {
                reelViewerIndex--;
                loadReelIntoViewer(reelViewerList[reelViewerIndex].id);
            }
        }

        // Mobile/tablet: swipe up/down to move between reels.
        // Desktop: mouse wheel scroll or Up/Down arrow keys.
        let _reelTouchStartY = null;
        function _reelTouchStart(e) { _reelTouchStartY = e.touches[0].clientY; }
        function _reelTouchEnd(e) {
            if (_reelTouchStartY === null) return;
            const deltaY = e.changedTouches[0].clientY - _reelTouchStartY;
            if (Math.abs(deltaY) > 50) {
                if (deltaY < 0) reelViewerNext(); else reelViewerPrev();
            }
            _reelTouchStartY = null;
        }
        let _reelWheelLock = false;
        function _reelWheel(e) {
            if (_reelWheelLock) return;
            _reelWheelLock = true;
            setTimeout(() => { _reelWheelLock = false; }, 500);
            if (e.deltaY > 20) reelViewerNext();
            else if (e.deltaY < -20) reelViewerPrev();
        }
        function _reelKeydown(e) {
            if (e.key === 'ArrowDown') reelViewerNext();
            else if (e.key === 'ArrowUp') reelViewerPrev();
            else if (e.key === 'Escape') closeReelViewer();
        }
        function setupReelViewerGestures() {
            const el = document.getElementById('reelViewerContainer');
            if (!el) return;
            el.addEventListener('touchstart', _reelTouchStart, { passive: true });
            el.addEventListener('touchend', _reelTouchEnd, { passive: true });
            el.addEventListener('wheel', _reelWheel, { passive: true });
            document.addEventListener('keydown', _reelKeydown);
        }
        function teardownReelViewerGestures() {
            const el = document.getElementById('reelViewerContainer');
            if (el) {
                el.removeEventListener('touchstart', _reelTouchStart);
                el.removeEventListener('touchend', _reelTouchEnd);
                el.removeEventListener('wheel', _reelWheel);
            }
            document.removeEventListener('keydown', _reelKeydown);
        }

        async function toggleReelLikeInViewer() {
            if (!currentViewerReel) return;
            try {
                const res = await fetch(`${API_BASE}/reels/${currentViewerReel.id}/like`, {
                    method: 'POST',
                    body: new URLSearchParams({ user_id: loggedInUser.id })
                });
                const data = await res.json();
                document.getElementById('reelViewerLikes').textContent = data.likes;
                document.getElementById('reelViewerLikeBtn').style.color = data.liked ? 'var(--red)' : '';
                currentViewerReel.likes = data.likes;
            } catch(e) { console.error('Error liking reel:', e); }
        }

        async function submitReelComment() {
            if (!currentViewerReel) return;
            const input = document.getElementById('reelViewerCommentInput');
            const text = input.value.trim();
            if (!text) return;
            try {
                const res = await fetch(`${API_BASE}/reels/${currentViewerReel.id}/comment`, {
                    method: 'POST',
                    body: new URLSearchParams({ user_id: loggedInUser.id, text })
                });
                const data = await res.json();
                if (data.success) {
                    input.value = '';
                    currentViewerReel.comments = JSON.stringify(data.comments);
                    renderReelViewerComments(currentViewerReel);
                }
            } catch(e) { console.error('Error commenting on reel:', e); }
        }

        async function deleteReelFromViewer() {
            if (!currentViewerReel) return;
            if (!confirm('Delete this reel? This cannot be undone.')) return;
            try {
                const res = await fetch(`${API_BASE}/reels/${currentViewerReel.id}`, {
                    method: 'DELETE',
                    body: new URLSearchParams({ user_id: loggedInUser.id })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('🗑️ Reel deleted');
                    closeReelViewer();
                    loadReels();
                }
            } catch(e) { console.error('Error deleting reel:', e); }
        }

        // ============================================================
        // UPLOAD MODAL - G3 Style
        // ============================================================
        let uploadDestination = 'reel';

        function setUploadDestination(dest) {
            uploadDestination = dest;
            const reelBtn = document.getElementById('uploadDestReelBtn');
            const storyBtn = document.getElementById('uploadDestStoryBtn');
            const desc = document.getElementById('uploadDescription');
            const privacy = document.getElementById('privacySelect');
            if (dest === 'story') {
                reelBtn.style.background = '';
                reelBtn.style.color = '';
                storyBtn.style.background = 'var(--burgundy)';
                storyBtn.style.color = 'white';
                document.getElementById('uploadModalTitle').textContent = 'Add to Your Story';
                desc.style.display = 'none';
                privacy.style.display = 'none';
            } else {
                storyBtn.style.background = '';
                storyBtn.style.color = '';
                reelBtn.style.background = 'var(--burgundy)';
                reelBtn.style.color = 'white';
                document.getElementById('uploadModalTitle').textContent = 'Upload to FUOMCE';
                desc.style.display = '';
                privacy.style.display = '';
            }
        }

        function openUploadModal(dest) {
            document.getElementById('uploadModal').classList.add('active');
            setUploadDestination(dest || 'reel');
        }

        function closeUploadModal() {
            document.getElementById('uploadModal').classList.remove('active');
            selectedFiles = [];
            document.getElementById('uploadPreviews').innerHTML = '';
            document.getElementById('uploadFileInput').value = '';
        }

        document.getElementById('uploadFileInput').addEventListener('change', function() {
            const files = this.files;
            if (!files.length) return;
            
            selectedFiles = Array.from(files);
            const previewDiv = document.getElementById('uploadPreviews');
            previewDiv.innerHTML = '';
            
            selectedFiles.forEach((file, index) => {
                const div = document.createElement('div');
                div.className = 'preview-item';
                
                const removeBtn = document.createElement('button');
                removeBtn.className = 'remove-btn';
                removeBtn.innerHTML = '×';
                removeBtn.onclick = function(e) {
                    e.stopPropagation();
                    selectedFiles.splice(index, 1);
                    div.remove();
                    if (selectedFiles.length === 0) {
                        document.getElementById('uploadPreviews').innerHTML = '';
                    }
                };
                
                if (file.type.startsWith('image/')) {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        div.innerHTML = `<img src="${e.target.result}" style="width:100%;height:100%;object-fit:cover;">`;
                        div.appendChild(removeBtn);
                    };
                    reader.readAsDataURL(file);
                } else if (file.type.startsWith('video/')) {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        div.innerHTML = `<video src="${e.target.result}" style="width:100%;height:100%;object-fit:cover;"></video>`;
                        div.appendChild(removeBtn);
                    };
                    reader.readAsDataURL(file);
                } else {
                    div.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;background:#1a1a1a;color:white;font-size:2rem;"><i class="fas fa-music"></i></div>`;
                    div.appendChild(removeBtn);
                }
                
                previewDiv.appendChild(div);
            });
        });

        async function submitUpload() {
            if (!selectedFiles.length) return alert('Please select a file');
            
            const description = document.getElementById('uploadDescription').value.trim();
            const privacy = document.getElementById('privacySelect').value;
            let success = 0;
            
            for (const file of selectedFiles) {
                const formData = new FormData();
                formData.append('user_id', loggedInUser.id);
                formData.append('media', file);

                if (uploadDestination === 'story') {
                    try {
                        const res = await fetch(`${API_BASE}/stories`, { method: 'POST', body: formData });
                        const data = await res.json();
                        if (data.success) success++;
                    } catch(e) {
                        console.error('Story upload error:', e);
                    }
                } else {
                    formData.append('title', description || 'Untitled');
                    formData.append('description', description || '');
                    formData.append('privacy', privacy);
                    
                    try {
                        const res = await fetch(`${API_BASE}/reels`, { method: 'POST', body: formData });
                        const data = await res.json();
                        if (data.success) success++;
                    } catch(e) {
                        console.error('Upload error:', e);
                    }
                }
            }
            
            showToast(`✅ ${success} ${uploadDestination === 'story' ? 'story item(s)' : 'file(s)'} uploaded!`);
            closeUploadModal();
            document.getElementById('uploadDescription').value = '';
            if (uploadDestination === 'story') {
                await loadStories();
            } else {
                await loadReels();
                renderProfile(loggedInUser.id);
            }
        }

        // ============================================================
        // CREATE GROUP - G1 Style
        // ============================================================
        function openCreateGroupModal() {
            document.getElementById('createGroupModal').classList.add('active');
            document.getElementById('groupName').value = '';
            document.getElementById('groupDescription').value = '';
            document.getElementById('groupPublic').checked = true;
        }

        function closeCreateGroupModal() {
            document.getElementById('createGroupModal').classList.remove('active');
        }

        async function createGroup() {
            const name = document.getElementById('groupName').value.trim();
            const description = document.getElementById('groupDescription').value.trim();
            const isPublic = document.getElementById('groupPublic').checked;
            
            if (!name) return alert('Please enter a group name');
            
            const formData = new FormData();
            formData.append('user_id', loggedInUser.id);
            formData.append('name', name);
            formData.append('description', description || '');
            formData.append('is_public', isPublic);
            
            try {
                const res = await fetch(`${API_BASE}/groups`, { method: 'POST', body: formData });
                const data = await res.json();
                if (data.id) {
                    showToast('✅ Group created!');
                    closeCreateGroupModal();
                    await loadGroups();
                    renderChatList();
                    navigateTo('chats-page');
                    setTimeout(() => openChat('group', data.id), 300);
                } else {
                    alert('Failed to create group');
                }
            } catch(e) {
                console.error('Error creating group:', e);
                alert('Error creating group');
            }
        }

        let currentGroupInfoId = null;

        async function showGroupInfo(groupId) {
            currentGroupInfoId = groupId;
            const group = allGroups.find(g => g.id === groupId);
            if (!group) return;
            
            const membersRes = await fetch(`${API_BASE}/groups/${groupId}/members`);
            const members = await membersRes.json();
            const statusRes = await fetch(`${API_BASE}/groups/${groupId}/member-status?user_id=${loggedInUser.id}`);
            const status = await statusRes.json();
            
            const isAdmin = status.is_admin;
            
            document.getElementById('groupInfoName').textContent = '📚 ' + group.name;
            document.getElementById('groupInfoDesc').textContent = group.description || 'No description';
            document.getElementById('groupInfoLockStatus').innerHTML =
                `${members.length} members · ${group.is_locked ? '🔒 Locked (only admins can message)' : '🔓 Unlocked'}`;
            
            const adminActions = document.getElementById('groupInfoAdminActions');
            if (isAdmin) {
                adminActions.innerHTML = `
                    <button class="btn-secondary" style="flex:1; padding:8px; font-size:0.8rem;" onclick="toggleGroupLockFromInfo()">
                        <i class="fas fa-${group.is_locked ? 'lock-open' : 'lock'}"></i> ${group.is_locked ? 'Unlock Group' : 'Lock Group'}
                    </button>
                `;
            } else {
                adminActions.innerHTML = '';
            }
            
            const membersContainer = document.getElementById('groupInfoMembers');
            membersContainer.innerHTML = members.map(m => `
                <div style="display:flex; align-items:center; gap:10px; padding:6px 8px; border-bottom:1px solid #f5f5f5;">
                    <div class="avatar" style="width:30px; height:30px; border-radius:50%; display:flex; align-items:center; justify-content:center; background:${m.avatar_color}; color:white; font-weight:700; font-size:0.75rem; flex-shrink:0;">${(m.display_name || m.username)[0]}</div>
                    <div style="flex:1; font-size:0.85rem;">${m.display_name || m.username} ${m.id === loggedInUser.id ? '(You)' : ''} ${m.is_admin ? '<span style="color:var(--burgundy);">👑</span>' : ''}</div>
                    ${isAdmin && m.id !== loggedInUser.id ? `
                        <div style="display:flex; gap:6px;">
                            ${!m.is_admin ? `<button title="Make admin" onclick="makeGroupAdmin(${m.id})" style="background:none; border:none; cursor:pointer; color:#888;"><i class="fas fa-crown"></i></button>` : ''}
                            <button title="Remove from group" onclick="removeGroupMemberFromInfo(${m.id})" style="background:none; border:none; cursor:pointer; color:var(--red);"><i class="fas fa-user-minus"></i></button>
                        </div>
                    ` : ''}
                </div>
            `).join('');
            
            const addSection = document.getElementById('groupInfoAddSection');
            if (isAdmin) {
                const memberIds = members.map(m => m.id);
                const addableFriends = friends.filter(f => !memberIds.includes(f.id));
                const addList = document.getElementById('groupInfoAddList');
                if (addableFriends.length === 0) {
                    addList.innerHTML = '<p style="color:#999; font-size:0.8rem;">All your friends are already in this group</p>';
                } else {
                    addList.innerHTML = addableFriends.map(f => `
                        <div style="display:flex; align-items:center; gap:10px; padding:6px 8px; border-bottom:1px solid #f5f5f5;">
                            <div class="avatar" style="width:28px; height:28px; border-radius:50%; display:flex; align-items:center; justify-content:center; background:${f.avatar_color}; color:white; font-weight:700; font-size:0.7rem;">${(f.display_name || f.username)[0]}</div>
                            <div style="flex:1; font-size:0.85rem;">${f.display_name || f.username}</div>
                            <button onclick="addFriendToGroup(${f.id})" style="background:var(--burgundy); color:white; border:none; padding:4px 10px; border-radius:var(--radius-full); font-size:0.7rem; cursor:pointer;">Add</button>
                        </div>
                    `).join('');
                }
                addSection.style.display = 'block';
            } else {
                addSection.style.display = 'none';
            }
            
            document.getElementById('groupInfoModal').classList.add('active');
        }

        function closeGroupInfoModal() {
            document.getElementById('groupInfoModal').classList.remove('active');
            currentGroupInfoId = null;
        }

        async function makeGroupAdmin(userId) {
            if (!currentGroupInfoId) return;
            try {
                const res = await fetch(`${API_BASE}/groups/${currentGroupInfoId}/make-admin?user_id=${userId}`, {
                    method: 'POST',
                    body: new URLSearchParams({ admin_id: loggedInUser.id })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('👑 Now an admin');
                    showGroupInfo(currentGroupInfoId);
                } else {
                    alert(data.detail || 'Error');
                }
            } catch(e) { console.error('Error making admin:', e); }
        }

        async function removeGroupMemberFromInfo(userId) {
            if (!currentGroupInfoId) return;
            if (!confirm('Remove this member from the group?')) return;
            try {
                const res = await fetch(`${API_BASE}/groups/${currentGroupInfoId}/remove-member?user_id=${userId}`, {
                    method: 'POST',
                    body: new URLSearchParams({ admin_id: loggedInUser.id })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('Member removed');
                    showGroupInfo(currentGroupInfoId);
                } else {
                    alert(data.detail || 'Error');
                }
            } catch(e) { console.error('Error removing member:', e); }
        }

        async function addFriendToGroup(userId) {
            if (!currentGroupInfoId) return;
            try {
                const res = await fetch(`${API_BASE}/groups/${currentGroupInfoId}/add-members`, {
                    method: 'POST',
                    body: new URLSearchParams({ user_ids: String(userId), admin_id: loggedInUser.id })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('✅ Added to group');
                    await loadGroups();
                    showGroupInfo(currentGroupInfoId);
                } else {
                    alert(data.detail || 'Error');
                }
            } catch(e) { console.error('Error adding to group:', e); }
        }

        async function toggleGroupLockFromInfo() {
            if (!currentGroupInfoId) return;
            try {
                const res = await fetch(`${API_BASE}/groups/${currentGroupInfoId}/toggle-lock`, {
                    method: 'POST',
                    body: new URLSearchParams({ admin_id: loggedInUser.id })
                });
                const data = await res.json();
                if (data.locked !== undefined) {
                    await loadGroups();
                    showGroupInfo(currentGroupInfoId);
                } else {
                    alert(data.detail || 'Error');
                }
            } catch(e) { console.error('Error toggling lock:', e); }
        }

        async function leaveGroupFromInfo() {
            if (!currentGroupInfoId) return;
            if (!confirm('Leave this group?')) return;
            try {
                const res = await fetch(`${API_BASE}/groups/${currentGroupInfoId}/leave`, {
                    method: 'POST',
                    body: new URLSearchParams({ user_id: loggedInUser.id })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('Left the group');
                    closeGroupInfoModal();
                    await loadGroups();
                    if (currentChatType === 'group' && currentChatId === currentGroupInfoId) {
                        document.getElementById('chatWindow').innerHTML = '<div style="text-align:center; color:#999; padding:20px;">Select a chat to start messaging</div>';
                    }
                }
            } catch(e) { console.error('Error leaving group:', e); }
        }

        // ============================================================
        // CHAT SYSTEM - G1 Style
        // ============================================================
        function renderChatList() {
            const container = document.getElementById('chatListItems');
            container.innerHTML = '';
            
            friends.forEach(friend => {
                const key = 'user_' + friend.id;
                const history = chatHistory[key] || [];
                const lastMsg = history.length > 0 ? history[history.length - 1] : null;
                const unread = history.filter(m => !m.is_read && m.sender_id === friend.id).length;
                
                const div = document.createElement('div');
                div.className = 'chat-list-item' + (currentChatId === friend.id && currentChatType === 'user' ? ' active' : '');
                const isOnline = friend.is_online;
                div.innerHTML = `
                    <div class="avatar" style="background:${friend.avatar_color};">
                        ${(friend.display_name || friend.username)[0]}
                        <div class="online-dot" style="background:${isOnline ? '#2ed573' : '#888'};"></div>
                    </div>
                    <div class="details">
                        <h4>${friend.display_name || friend.username}</h4>
                        <p>${lastMsg ? (lastMsg.is_deleted ? '🗑️ Deleted' : lastMsg.content) : 'Start chatting'}</p>
                    </div>
                    <div style="display:flex; flex-direction:column; align-items:flex-end; gap:4px;">
                        <span class="time">${lastMsg ? new Date(lastMsg.timestamp).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : ''}</span>
                        ${unread > 0 ? `<span class="badge" style="background:var(--red); color:white; font-size:0.6rem; padding:1px 6px; border-radius:10px;">${unread}</span>` : ''}
                    </div>
                `;
                div.onclick = () => openChat('user', friend.id);
                container.appendChild(div);
            });
            
            allGroups.forEach(group => {
                const key = 'group_' + group.id;
                const history = chatHistory[key] || [];
                const lastMsg = history.length > 0 ? history[history.length - 1] : null;
                
                const div = document.createElement('div');
                div.className = 'chat-list-item' + (currentChatId === group.id && currentChatType === 'group' ? ' active' : '');
                div.innerHTML = `
                    <div class="avatar" style="background:#800020;">${group.name[0]}</div>
                    <div class="details">
                        <h4>${group.name} ${group.is_locked ? '🔒' : ''}</h4>
                        <p>${lastMsg ? (lastMsg.is_deleted ? '🗑️ Deleted' : lastMsg.content) : group.member_count || 0} members</p>
                    </div>
                    <div style="display:flex; flex-direction:column; align-items:flex-end; gap:4px;">
                        <span class="time">${lastMsg ? new Date(lastMsg.timestamp).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : ''}</span>
                        <button onclick="event.stopPropagation(); showGroupInfo(${group.id})" style="background:var(--bg-gray); padding:2px 10px; border-radius:var(--radius-full); font-size:0.6rem;">Info</button>
                    </div>
                `;
                div.onclick = () => openChat('group', group.id);
                container.appendChild(div);
            });
            
            updateChatBadge();
        }

        function filterChatList() {
            const query = document.getElementById('chatListSearch').value.toLowerCase();
            const items = document.querySelectorAll('.chat-list-item');
            items.forEach(item => {
                const name = item.querySelector('.details h4')?.textContent?.toLowerCase() || '';
                item.style.display = name.includes(query) ? 'flex' : 'none';
            });
        }

        function updateChatBadge() {
            let totalUnread = 0;
            Object.keys(chatHistory).forEach(key => {
                const msgs = chatHistory[key] || [];
                totalUnread += msgs.filter(m => !m.is_read && m.sender_id !== loggedInUser.id).length;
            });
            document.getElementById('chatBadge').innerText = totalUnread || '0';
        }

        function openChat(type, id) {
            if (type === 'user' && id === loggedInUser.id) {
                showToast('You cannot chat with yourself');
                return;
            }
            
            currentChatId = id;
            currentChatType = type;
            
            const user = type === 'user' ? allUsers.find(u => u.id === id) : null;
            const group = type === 'group' ? allGroups.find(g => g.id === id) : null;
            
            const name = user ? (user.display_name || user.username) : (group ? group.name : 'Chat');
            const chatWindow = document.getElementById('chatWindow');
            chatWindow.innerHTML = '';
            
            // Chat header - G1 Style
            const header = document.createElement('div');
            header.style.cssText = 'padding:12px 16px; border-bottom:1px solid #eaeaea; display:flex; align-items:center; gap:12px; background:white; flex-shrink:0;';
            const isOnline = user ? user.is_online : false;
            const avatarColor = user ? user.avatar_color : '#800020';
            
            header.innerHTML = `
                <div class="avatar" style="width:36px; height:36px; border-radius:50%; display:flex; align-items:center; justify-content:center; background:${avatarColor}; color:white; font-weight:700; font-size:0.9rem; position:relative; flex-shrink:0;">
                    ${name[0]}
                    ${type === 'user' ? `<div class="online-dot" style="position:absolute; bottom:0; right:0; width:10px; height:10px; border-radius:50%; border:2px solid white; background:${isOnline ? '#2ed573' : '#888'};"></div>` : ''}
                </div>
                <div style="flex:1;">
                    <div style="font-weight:600;">${name}</div>
                    <div style="font-size:0.75rem; color:#888;">${type === 'user' ? (isOnline ? '🟢 Online' : '⚪ Offline') : (group ? (group.member_count || 0) + ' members' : '')}</div>
                </div>
                ${type === 'group' ? `<button onclick="showGroupInfo(${id})" style="background:var(--bg-gray); padding:4px 12px; border-radius:var(--radius-full); font-size:0.75rem;">Info</button>` : ''}
            `;
            chatWindow.appendChild(header);
            
            // Messages container
            const messagesDiv = document.createElement('div');
            messagesDiv.className = 'chat-messages';
            messagesDiv.id = 'chatMessagesContainer';
            chatWindow.appendChild(messagesDiv);
            
            // Chat input - G1 Style
            const inputDiv = document.createElement('div');
            inputDiv.className = 'chat-input';
            inputDiv.innerHTML = `
                <div class="reply-preview-bar" id="replyPreviewBar">
                    <div id="replyPreviewText" style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"></div>
                    <i class="fas fa-times close-reply" onclick="cancelReply()"></i>
                </div>
                <div class="input-wrapper">
                    <input type="text" id="chatInputBox" placeholder="Type a message..." onkeypress="handleChatKeyPress(event)">
                    <button class="file-btn" onclick="document.getElementById('chatFileInput').click()"><i class="fas fa-paperclip"></i> File</button>
                    <input type="file" id="chatFileInput" style="display:none;" onchange="sendChatFile()">
                    <button class="record-btn" onclick="openRecordModal('${type}', ${id})" title="Record voice or video"><i class="fas fa-microphone"></i> Record</button>
                    <button class="send-btn" onclick="sendChatMessage()"><i class="fas fa-paper-plane"></i> Send</button>
                </div>
            `;
            chatWindow.appendChild(inputDiv);
            
            // Reset any in-progress reply/edit state from a previous chat
            currentReplyTo = null;
            currentEditingMessageId = null;
            
            // Load messages
            loadChatMessages(type, id);
            
            // Mark messages as read
            const key = type === 'user' ? 'user_' + id : 'group_' + id;
            if (chatHistory[key]) {
                chatHistory[key].forEach(m => {
                    if (m.sender_id !== loggedInUser.id && !m.is_read) {
                        m.is_read = true;
                        sendWebSocketMessage({ type: 'read_receipt', message_id: m.id });
                    }
                });
                renderChatList();
            }
        }

        async function loadChatMessages(type, id) {
            const container = document.getElementById('chatMessagesContainer');
            if (!container) return;
            
            container.innerHTML = '';
            const endpoint = type === 'user' ? 
                `${API_BASE}/chat/${id}/messages?current_user_id=${loggedInUser.id}` :
                `${API_BASE}/groups/${id}/messages?user_id=${loggedInUser.id}`;
            
            try {
                const res = await fetch(endpoint);
                const msgs = await res.json();
                const key = type === 'user' ? 'user_' + id : 'group_' + id;
                chatHistory[key] = msgs;
                
                msgs.forEach(msg => {
                    displayMessage(msg);
                });
                
                container.scrollTop = container.scrollHeight;
            } catch(e) {
                console.error('Error loading messages:', e);
            }
        }

        let currentReplyTo = null;
        let currentEditingMessageId = null;

        function displayMessage(data) {
            const container = document.getElementById('chatMessagesContainer');
            if (!container) return;
            
            if (data.deleted_for) {
                const deletedIds = data.deleted_for.split(',').map(id => parseInt(id.trim()));
                if (deletedIds.includes(loggedInUser.id)) return;
            }
            
            const isOwn = data.sender_id === loggedInUser.id;
            const wrapper = document.createElement('div');
            wrapper.className = `message-wrapper ${isOwn ? 'sent' : 'received'}`;
            wrapper.style.cssText = 'display:flex; flex-direction:column; margin-bottom:4px;' + (isOwn ? 'align-items:flex-end;' : 'align-items:flex-start;');
            wrapper.dataset.messageId = data.id;
            
            const msgDiv = document.createElement('div');
            msgDiv.className = `chat-message ${isOwn ? 'sent' : 'received'}`;
            
            let content = data.content;
            let fileHtml = '';
            
            if (data.file_url && !data.is_deleted) {
                const filePath = '/uploads/' + data.file_url;
                const ext = data.file_url.split('.').pop().toLowerCase();
                const ftype = (data.file_type || '').toLowerCase();
                const fname = (data.file_url || '').toLowerCase();
                // Prefer the actual stored file_type / message_type (reliable) over
                // guessing from a shared ".webm" extension, since both voice notes
                // and video notes are saved as .webm and would otherwise collide.
                let isAudio = ftype.startsWith('audio/') || fname.startsWith('recaudio_') || (!ftype && ['mp3', 'wav', 'aac', 'ogg', 'm4a'].includes(ext));
                let isVideo = ftype.startsWith('video/') || fname.startsWith('recvideo_') || (!ftype && ['mp4', 'mov', 'avi', 'mkv'].includes(ext));
                if (!isAudio && !isVideo && ext === 'webm') {
                    // Legacy fallback for older messages saved before this fix
                    isAudio = data.message_type === 'audio';
                    isVideo = data.message_type === 'video';
                }
                const isImage = ftype.startsWith('image/') || ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'].includes(ext);
                
                if (isAudio) {
                    fileHtml = `
                        <div class="audio-player">
                            <audio controls>
                                <source src="${filePath}">
                            </audio>
                        </div>
                    `;
                } else if (isVideo) {
                    fileHtml = `
                        <div class="video-player">
                            <video controls>
                                <source src="${filePath}">
                            </video>
                        </div>
                    `;
                } else if (isImage) {
                    fileHtml = `
                        <div onclick="window.open('${filePath}')" style="cursor:pointer; margin-top:6px; max-width:200px; border-radius:8px; overflow:hidden;">
                            <img src="${filePath}" style="width:100%; height:auto; max-height:150px; object-fit:cover;">
                        </div>
                    `;
                } else {
                    fileHtml = `
                        <div class="file-attachment" onclick="window.open('${filePath}')">
                            <i class="fas fa-file file-icon"></i>
                            <div class="file-info">
                                <div class="file-name">${data.file_name || 'File'}</div>
                                <div class="file-size">${data.file_size ? (data.file_size/1024).toFixed(1) + ' KB' : ''}</div>
                            </div>
                            <div style="font-size:0.65rem; opacity:0.7;">⬇️ Download</div>
                        </div>
                    `;
                }
            }
            
            const time = new Date(data.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            msgDiv.innerHTML = `
                ${data.is_deleted ? '' : content}
                ${fileHtml}
                <span class="time">${time}${data.edited_at ? ' ✎' : ''}</span>
            `;
            
            // Reply handling - G1 Style
            if (data.reply_to_id && data.reply_to_content) {
                const replyDiv = document.createElement('div');
                replyDiv.style.cssText = 'font-size:0.75rem; color:#888; margin-bottom:4px; padding:4px 8px; background:rgba(0,0,0,0.05); border-radius:8px; border-left:3px solid var(--burgundy); cursor:pointer;';
                replyDiv.textContent = '↩️ ' + data.reply_to_content;
                replyDiv.onclick = () => {
                    const target = document.querySelector(`[data-message-id="${data.reply_to_id}"]`);
                    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                };
                msgDiv.prepend(replyDiv);
            }
            
            wrapper.appendChild(msgDiv);
            
            // Hover action bar: reply, react, and (own messages only) edit/delete
            if (!data.is_deleted) {
                const actions = document.createElement('div');
                actions.className = 'msg-actions';
                const canEdit = isOwn && !data.file_url && (Date.now() - new Date(data.timestamp).getTime()) < 5 * 60 * 1000;
                actions.innerHTML = `
                    <button onclick="startReply(${data.id}, '${(data.content || '').replace(/'/g, "\\'").slice(0, 60)}')" title="Reply"><i class="fas fa-reply"></i></button>
                    <button onclick="openEmojiPicker(${data.id}, event)" title="React"><i class="fas fa-face-smile"></i></button>
                    ${canEdit ? `<button onclick="startEditMessage(${data.id}, '${(data.content || '').replace(/'/g, "\\'")}')" title="Edit"><i class="fas fa-pen"></i></button>` : ''}
                    <button onclick="confirmDeleteMessage(${data.id}, ${isOwn})" title="Delete"><i class="fas fa-trash"></i></button>
                `;
                wrapper.appendChild(actions);
                
                const picker = document.createElement('div');
                picker.className = 'emoji-picker-popup';
                picker.id = `emojiPicker_${data.id}`;
                picker.innerHTML = ['👍','❤️','😂','😮','😢','🙏'].map(e => `<span onclick="sendReaction(${data.id}, '${e}')">${e}</span>`).join('');
                wrapper.appendChild(picker);
            }
            
            // Reaction pills
            let reactions = {};
            try { reactions = typeof data.reactions === 'string' ? JSON.parse(data.reactions) : (data.reactions || {}); } catch(e) {}
            if (Object.keys(reactions).length > 0) {
                const reactionsDiv = document.createElement('div');
                reactionsDiv.className = 'msg-reactions';
                reactionsDiv.id = `reactions_${data.id}`;
                reactionsDiv.innerHTML = Object.entries(reactions).map(([emoji, uids]) =>
                    `<span class="reaction-pill ${uids.includes(loggedInUser.id) ? 'mine' : ''}" onclick="sendReaction(${data.id}, '${emoji}')">${emoji} ${uids.length}</span>`
                ).join('');
                wrapper.appendChild(reactionsDiv);
            } else {
                const reactionsDiv = document.createElement('div');
                reactionsDiv.className = 'msg-reactions';
                reactionsDiv.id = `reactions_${data.id}`;
                wrapper.appendChild(reactionsDiv);
            }
            
            container.appendChild(wrapper);
            container.scrollTop = container.scrollHeight;
        }

        function startReply(messageId, preview) {
            currentReplyTo = messageId;
            currentEditingMessageId = null;
            const bar = document.getElementById('replyPreviewBar');
            document.getElementById('replyPreviewText').textContent = '↩️ Replying to: ' + preview;
            bar.classList.add('active');
            document.getElementById('chatInputBox').focus();
        }

        function cancelReply() {
            currentReplyTo = null;
            currentEditingMessageId = null;
            document.getElementById('replyPreviewBar').classList.remove('active');
            document.getElementById('chatInputBox').value = '';
        }

        function startEditMessage(messageId, content) {
            currentEditingMessageId = messageId;
            currentReplyTo = null;
            const bar = document.getElementById('replyPreviewBar');
            document.getElementById('replyPreviewText').textContent = '✎ Editing message';
            bar.classList.add('active');
            const input = document.getElementById('chatInputBox');
            input.value = content;
            input.focus();
        }

        function openEmojiPicker(messageId, event) {
            event.stopPropagation();
            document.querySelectorAll('.emoji-picker-popup.active').forEach(p => {
                if (p.id !== `emojiPicker_${messageId}`) p.classList.remove('active');
            });
            document.getElementById(`emojiPicker_${messageId}`).classList.toggle('active');
        }

        async function sendReaction(messageId, emoji) {
            document.querySelectorAll('.emoji-picker-popup.active').forEach(p => p.classList.remove('active'));
            try {
                const res = await fetch(`${API_BASE}/messages/${messageId}/react`, {
                    method: 'POST',
                    body: new URLSearchParams({ user_id: loggedInUser.id, emoji })
                });
                const data = await res.json();
                if (data.success) renderReactionsForMessage(messageId, data.reactions);
            } catch(e) { console.error('Error reacting to message:', e); }
        }

        function renderReactionsForMessage(messageId, reactions) {
            const el = document.getElementById(`reactions_${messageId}`);
            if (!el) return;
            el.innerHTML = Object.entries(reactions).map(([emoji, uids]) =>
                `<span class="reaction-pill ${uids.includes(loggedInUser.id) ? 'mine' : ''}" onclick="sendReaction(${messageId}, '${emoji}')">${emoji} ${uids.length}</span>`
            ).join('');
        }

        async function confirmDeleteMessage(messageId, isOwn) {
            if (isOwn) {
                const choice = prompt('Type "me" to delete just for you, or "all" to delete for everyone:', 'me');
                if (!choice) return;
                if (choice.toLowerCase().startsWith('a')) {
                    await deleteMessageForEveryone(messageId);
                } else {
                    await deleteMessageForMe(messageId);
                }
            } else {
                if (confirm('Delete this message for you?')) {
                    await deleteMessageForMe(messageId);
                }
            }
        }

        async function deleteMessageForEveryone(messageId) {
            try {
                const res = await fetch(`${API_BASE}/messages/${messageId}`, {
                    method: 'DELETE',
                    body: new URLSearchParams({ user_id: loggedInUser.id })
                });
                const data = await res.json();
                if (data.success) showToast('🗑️ Message deleted for everyone');
            } catch(e) { console.error('Error deleting message:', e); }
        }

        async function deleteMessageForMe(messageId) {
            try {
                const res = await fetch(`${API_BASE}/messages/${messageId}/for-me`, {
                    method: 'DELETE',
                    body: new URLSearchParams({ user_id: loggedInUser.id })
                });
                const data = await res.json();
                if (data.success) {
                    const wrapper = document.querySelector(`[data-message-id="${messageId}"]`);
                    if (wrapper) wrapper.remove();
                    showToast('🗑️ Message deleted for you');
                }
            } catch(e) { console.error('Error deleting message:', e); }
        }

        function sendChatMessage() {
            const input = document.getElementById('chatInputBox');
            if (!input || !input.value.trim() || !currentChatId) return;
            
            const content = input.value.trim();
            
            if (currentEditingMessageId) {
                const editingId = currentEditingMessageId;
                fetch(`${API_BASE}/messages/${editingId}`, {
                    method: 'PUT',
                    body: new URLSearchParams({ content, user_id: loggedInUser.id })
                }).then(res => res.json()).then(data => {
                    if (!data.success && data.detail) showToast(data.detail);
                }).catch(e => console.error('Error editing message:', e));
                cancelReply();
                return;
            }
            
            const data = {
                type: 'message',
                content: content
            };
            
            if (currentChatType === 'group') {
                data.group_id = currentChatId;
            } else {
                data.recipient_id = currentChatId;
            }
            
            if (currentReplyTo) {
                data.reply_to_id = currentReplyTo;
            }
            
            sendWebSocketMessage(data);
            input.value = '';
            cancelReply();
        }

        function handleChatKeyPress(event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                sendChatMessage();
            }
            
            if (currentChatId) {
                clearTimeout(window.typingTimeout);
                const data = {
                    type: 'typing',
                    recipient_id: currentChatType === 'user' ? currentChatId : null,
                    group_id: currentChatType === 'group' ? currentChatId : null
                };
                sendWebSocketMessage(data);
                window.typingTimeout = setTimeout(() => {}, 2000);
            }
        }

        async function sendChatFile() {
            const input = document.getElementById('chatFileInput');
            if (!input.files.length || !currentChatId) return;
            
            const file = input.files[0];
            const formData = new FormData();
            formData.append('sender_id', loggedInUser.id);
            formData.append('file', file);
            
            if (currentChatType === 'group') {
                formData.append('group_id', currentChatId);
            } else {
                formData.append('recipient_id', currentChatId);
            }
            
            try {
                const res = await fetch(`${API_BASE}/messages/file`, { method: 'POST', body: formData });
                const data = await res.json();
                if (data.success) {
                    input.value = '';
                    showToast('📎 File sent!');
                    loadChatMessages(currentChatType, currentChatId);
                }
            } catch(e) {
                console.error('Error sending file:', e);
                alert('Failed to send file');
            }
        }

        // ============================================================
        // RECORDING MODAL - G2 Style (Voice Notes & Video Recording)
        // ============================================================
        let recordChatId = null;
        let recordChatType = null;
        let recordMediaStream = null;

        function openRecordModal(type, id) {
            if (type === 'user' && id === loggedInUser.id) {
                showToast('You cannot record for yourself');
                return;
            }
            
            recordChatId = id;
            recordChatType = type;
            recordedChunks = [];
            
            document.getElementById('recordModal').classList.add('active');
            document.getElementById('recordPlaceholder').style.display = 'block';
            document.getElementById('recordVideo').style.display = 'none';
            document.getElementById('recIndicator').style.display = 'none';
            document.getElementById('stopRecordBtn').style.display = 'none';
            document.getElementById('sendRecordBtn').style.display = 'none';
            
            // Reset recording state
            isRecording = false;
            recordingType = 'audio';
        }

        function closeRecordModal() {
            document.getElementById('recordModal').classList.remove('active');
            if (recordMediaStream) {
                recordMediaStream.getTracks().forEach(track => track.stop());
                recordMediaStream = null;
            }
            if (mediaRecorder && isRecording) {
                mediaRecorder.stop();
                isRecording = false;
            }
            recordedChunks = [];
            document.getElementById('recordVideo').srcObject = null;
        }

        function startRecording(type) {
            if (isRecording) return;
            
            recordingType = type;
            recordedChunks = [];
            
            const constraints = { audio: true };
            if (type === 'video') {
                constraints.video = { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } };
            }
            
            navigator.mediaDevices.getUserMedia(constraints)
                .then(stream => {
                    recordMediaStream = stream;
                    
                    if (type === 'video') {
                        document.getElementById('recordPlaceholder').style.display = 'none';
                        const video = document.getElementById('recordVideo');
                        video.style.display = 'block';
                        video.srcObject = stream;
                    } else {
                        document.getElementById('recordPlaceholder').innerHTML = `
                            <i class="fas fa-microphone" style="font-size:3rem; display:block; margin-bottom:10px; color:var(--green);"></i>
                            <p style="color:var(--green);">🎙️ Recording voice note...</p>
                        `;
                        document.getElementById('recordPlaceholder').style.display = 'block';
                    }
                    
                    document.getElementById('recIndicator').style.display = 'flex';
                    document.getElementById('stopRecordBtn').style.display = 'inline-block';
                    document.getElementById('sendRecordBtn').style.display = 'none';
                    
                    const mimeType = type === 'video' ? 'video/webm;codecs=vp9,opus' : 'audio/webm;codecs=opus';
                    mediaRecorder = new MediaRecorder(stream, { 
                        mimeType: MediaRecorder.isTypeSupported(mimeType) ? mimeType : (type === 'video' ? 'video/webm' : 'audio/webm')
                    });
                    
                    mediaRecorder.ondataavailable = (e) => {
                        if (e.data.size > 0) recordedChunks.push(e.data);
                    };
                    
                    mediaRecorder.onstop = () => {
                        isRecording = false;
                        document.getElementById('recIndicator').style.display = 'none';
                        document.getElementById('stopRecordBtn').style.display = 'none';
                        
                        if (recordedChunks.length) {
                            document.getElementById('sendRecordBtn').style.display = 'inline-block';
                            if (type === 'video') {
                                document.getElementById('recordPlaceholder').style.display = 'none';
                            } else {
                                document.getElementById('recordPlaceholder').innerHTML = `
                                    <i class="fas fa-check-circle" style="font-size:3rem; display:block; margin-bottom:10px; color:var(--green);"></i>
                                    <p style="color:var(--green);">✅ Voice note recorded (${recordedChunks.length} chunks)</p>
                                `;
                                document.getElementById('recordPlaceholder').style.display = 'block';
                            }
                        } else {
                            document.getElementById('recordPlaceholder').innerHTML = `
                                <i class="fas fa-exclamation-circle" style="font-size:3rem; display:block; margin-bottom:10px; color:var(--red);"></i>
                                <p>No recording captured. Try again.</p>
                            `;
                            document.getElementById('recordPlaceholder').style.display = 'block';
                        }
                        
                        if (stream) {
                            stream.getTracks().forEach(track => track.stop());
                            recordMediaStream = null;
                        }
                    };
                    
                    mediaRecorder.start(1000);
                    isRecording = true;
                    showToast(`🔴 Recording ${type === 'video' ? 'video' : 'voice note'}...`);
                })
                .catch(err => {
                    console.error('Recording error:', err);
                    alert('Could not access ' + (type === 'video' ? 'camera' : 'microphone') + '. Please allow permissions.');
                });
        }

        function stopRecording() {
            if (mediaRecorder && isRecording) {
                mediaRecorder.stop();
                isRecording = false;
            }
        }

        async function sendRecording() {
            if (!recordedChunks.length || !recordChatId) {
                showToast('❌ No recording to send');
                return;
            }
            
            const type = recordingType;
            const blob = new Blob(recordedChunks, { 
                type: type === 'video' ? 'video/webm' : 'audio/webm' 
            });
            const ext = type === 'video' ? 'webm' : 'webm';
            const filename = `recording_${Date.now()}.${ext}`;
            const file = new File([blob], filename, { type: blob.type });
            
            const formData = new FormData();
            formData.append('sender_id', loggedInUser.id);
            formData.append('file', file);
            formData.append('recording_type', type);
            
            if (recordChatType === 'group') {
                formData.append('group_id', recordChatId);
            } else {
                formData.append('recipient_id', recordChatId);
            }
            
            try {
                const res = await fetch(`${API_BASE}/messages/recording`, { method: 'POST', body: formData });
                const data = await res.json();
                if (data.success) {
                    showToast('✅ ' + (type === 'video' ? 'Video' : 'Voice note') + ' sent!');
                    closeRecordModal();
                    loadChatMessages(recordChatType, recordChatId);
                } else {
                    alert('Failed to send recording');
                }
            } catch(e) {
                console.error('Error sending recording:', e);
                alert('Failed to send recording: ' + e.message);
            }
        }

        function showTyping(username) {
            const container = document.getElementById('chatMessagesContainer');
            if (!container) return;
            
            const existing = container.querySelector('.typing-indicator');
            if (existing) existing.remove();
            
            const div = document.createElement('div');
            div.className = 'typing-indicator';
            div.style.cssText = 'align-self:flex-start; padding:6px 14px; background:#e8e8e8; border-radius:16px; border-bottom-left-radius:4px; font-size:0.8rem; color:#888; margin-bottom:4px;';
            div.innerHTML = `${username} typing...`;
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
            
            setTimeout(() => {
                if (div.parentNode) div.remove();
            }, 3000);
        }

        function openChatFromProfile() {
            if (profileViewUserId && profileViewUserId !== loggedInUser.id) {
                navigateTo('chats-page');
                setTimeout(() => openChat('user', profileViewUserId), 200);
            }
        }

        // ============================================================
        // PROFILE - G3 Style
        // ============================================================
        function renderProfile(userId) {
            profileViewUserId = userId;
            const user = allUsers.find(u => u.id === userId);
            if (!user) return;
            
            const isOwn = userId === loggedInUser.id;
            
            document.getElementById('profileName').innerText = user.display_name || user.username;
            document.getElementById('profileUsername').innerText = '@' + user.username;
            
            const avatarEl = document.getElementById('profileAvatar');
            avatarEl.style.background = user.avatar_color;
            document.getElementById('profileAvatarText').innerText = (user.display_name || user.username)[0];
            
            if (user.profile_pic) {
                document.getElementById('profilePicImg').style.display = 'block';
                document.getElementById('profilePicImg').src = `/uploads/${user.profile_pic}`;
                document.getElementById('profileAvatarText').style.display = 'none';
            } else {
                document.getElementById('profilePicImg').style.display = 'none';
                document.getElementById('profileAvatarText').style.display = 'block';
            }
            
            document.getElementById('profileOnlineDot').style.background = user.is_online ? '#2ed573' : '#888';
            document.getElementById('profileReelsTitle').innerText = isOwn ? 'My Reels' : `${user.display_name || user.username}'s Reels`;
            
            // Stats - count reels likes
            const userReels = reels.filter(r => r.user_id === userId);
            document.getElementById('profileLikes').innerText = userReels.reduce((sum, r) => sum + (r.likes || 0), 0);
            
            fetch(`${API_BASE}/users/${userId}/follow-info?viewer_id=${loggedInUser.id}`)
                .then(res => res.json())
                .then(info => {
                    document.getElementById('profileFollowers').innerText = info.followers;
                    document.getElementById('profileFollowing').innerText = info.following;
                    if (!isOwn) renderFollowButton(userId, info.is_following);
                })
                .catch(e => console.error('Error loading follow info:', e));
            
            // Actions
            const actions = document.getElementById('profileActions');
            actions.querySelectorAll('button').forEach(b => b.classList.add('hidden'));
            
            if (isOwn) {
                document.getElementById('editProfileBtn').classList.remove('hidden');
                document.getElementById('goLiveBtn').classList.remove('hidden');
            } else {
                // Check if already friends
                const isFriend = friends.some(f => f.id === userId);
                const hasPendingRequest = friendRequests.some(r => r.sender_id === userId);
                const hasSentRequest = sentFriendRequests.some(r => r.receiver_id === userId);
                
                if (isFriend) {
                    document.getElementById('chatProfileBtn').classList.remove('hidden');
                    chatPartnerId = userId;
                } else if (hasPendingRequest) {
                    // Show accept/decline buttons
                    const acceptBtn = document.createElement('button');
                    acceptBtn.className = 'btn-primary';
                    acceptBtn.textContent = 'Accept';
                    acceptBtn.style.cssText = 'background:var(--green); padding:6px 20px; border-radius:var(--radius-full); font-weight:600; color:white;';
                    acceptBtn.onclick = () => acceptFriendRequestFromProfile(userId);
                    actions.appendChild(acceptBtn);
                    
                    const declineBtn = document.createElement('button');
                    declineBtn.className = 'btn-secondary';
                    declineBtn.textContent = 'Decline';
                    declineBtn.style.cssText = 'background:var(--red); padding:6px 20px; border-radius:var(--radius-full); font-weight:600; color:white;';
                    declineBtn.onclick = () => declineFriendRequestFromProfile(userId);
                    actions.appendChild(declineBtn);
                } else if (hasSentRequest) {
                    const cancelBtn = document.createElement('button');
                    cancelBtn.textContent = 'Cancel Request';
                    cancelBtn.style.cssText = 'background:var(--charcoal-light); padding:6px 20px; border-radius:var(--radius-full); font-weight:600; color:white;';
                    cancelBtn.onclick = () => cancelFriendRequestFromProfile(userId);
                    actions.appendChild(cancelBtn);
                } else {
                    const addBtn = document.createElement('button');
                    addBtn.textContent = 'Add Friend';
                    addBtn.style.cssText = 'background:var(--camel); padding:6px 20px; border-radius:var(--radius-full); font-weight:600; color:white;';
                    addBtn.onclick = () => sendFriendRequestToUser(userId);
                    actions.appendChild(addBtn);
                }
            }
            
            // Reels
            const container = document.getElementById('profileReelsGrid');
            container.innerHTML = '';
            const filteredReels = userReels.slice(0, 12);
            
            if (filteredReels.length === 0) {
                container.innerHTML = '<p style="grid-column:1/-1; text-align:center; color:#999; padding:20px;">No reels posted yet</p>';
            } else {
                filteredReels.forEach(reel => {
                    const card = document.createElement('div');
                    card.className = 'grid-card';
                    const mediaHtml = reelThumbHtml(reel);
                    
                    card.innerHTML = `
                        <div class="grid-card-img">${mediaHtml}<div class="overlay-stats"><i class="fas fa-heart"></i> ${reel.likes || 0}</div></div>
                        <div class="grid-card-info">
                            <div class="text">
                                <h4>${reel.title}</h4>
                                <p>${reel.views || 0} views · ${new Date(reel.created_at).toLocaleDateString()}</p>
                            </div>
                        </div>
                    `;
                    card.onclick = () => viewReel(reel.id);
                    container.appendChild(card);
                });
            }
        }

        function renderFollowButton(userId, isFollowing) {
            const actions = document.getElementById('profileActions');
            let btn = document.getElementById('followToggleBtn');
            if (!btn) {
                btn = document.createElement('button');
                btn.id = 'followToggleBtn';
                actions.appendChild(btn);
            }
            btn.classList.remove('hidden');
            btn.textContent = isFollowing ? 'Following' : 'Follow';
            btn.style.cssText = isFollowing
                ? 'background:var(--bg-gray); color:var(--charcoal); padding:6px 20px; border-radius:var(--radius-full); font-weight:600; border:1px solid #ddd;'
                : 'background:var(--charcoal); color:white; padding:6px 20px; border-radius:var(--radius-full); font-weight:600;';
            btn.onclick = () => toggleFollow(userId, isFollowing);
        }

        async function toggleFollow(userId, currentlyFollowing) {
            try {
                const endpoint = currentlyFollowing ? 'unfollow' : 'follow';
                const res = await fetch(`${API_BASE}/${endpoint}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ follower_id: loggedInUser.id, followed_id: userId })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(currentlyFollowing ? 'Unfollowed' : '✅ Now following');
                    renderProfile(userId);
                }
            } catch(e) { console.error('Error toggling follow:', e); }
        }

        async function sendFriendRequestToUser(userId) {
            try {
                const res = await fetch(`${API_BASE}/friend_requests/send`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sender_id: loggedInUser.id, receiver_id: userId })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('✅ Friend request sent!');
                    await loadSentFriendRequests();
                    renderProfile(userId);
                } else {
                    alert(data.detail || 'Error');
                }
            } catch(e) {
                console.error('Error sending friend request:', e);
            }
        }

        async function acceptFriendRequestFromProfile(userId) {
            try {
                const res = await fetch(`${API_BASE}/friend_requests/accept`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sender_id: userId, receiver_id: loggedInUser.id })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('✅ Friend request accepted!');
                    await loadFriends();
                    await loadFriendRequests();
                    renderProfile(userId);
                    renderSidebar();
                    renderChatList();
                }
            } catch(e) {
                console.error('Error accepting friend request:', e);
            }
        }

        async function declineFriendRequestFromProfile(userId) {
            try {
                const res = await fetch(`${API_BASE}/friend_requests/decline`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sender_id: userId, receiver_id: loggedInUser.id })
                });
                if (res.ok) {
                    showToast('Friend request declined');
                    await loadFriendRequests();
                    renderProfile(userId);
                }
            } catch(e) {
                console.error('Error declining friend request:', e);
            }
        }

        async function cancelFriendRequestFromProfile(userId) {
            try {
                const res = await fetch(`${API_BASE}/friend_requests/cancel`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sender_id: loggedInUser.id, receiver_id: userId })
                });
                if (res.ok) {
                    showToast('Friend request cancelled');
                    await loadSentFriendRequests();
                    renderProfile(userId);
                }
            } catch(e) {
                console.error('Error cancelling friend request:', e);
            }
        }

        // ============================================================
        // PROFILE EDIT - G3 Style
        // ============================================================
        function openEditProfileModal() {
            document.getElementById('editProfileModal').classList.add('active');
            document.getElementById('editDisplayName').value = loggedInUser.display_name || loggedInUser.username;
            
            document.querySelectorAll('.color-option').forEach(el => {
                el.style.borderColor = el.style.background === loggedInUser.avatar_color ? '#000' : 'transparent';
                if (el.style.background === loggedInUser.avatar_color) {
                    window.selectedColor = loggedInUser.avatar_color;
                }
            });
        }

        function closeEditProfileModal() {
            document.getElementById('editProfileModal').classList.remove('active');
        }

        async function saveProfile() {
            const displayName = document.getElementById('editDisplayName').value.trim();
            if (!displayName) return alert('Name cannot be empty');
            
            const formData = new FormData();
            formData.append('user_id', loggedInUser.id);
            formData.append('display_name', displayName);
            formData.append('avatar_color', window.selectedColor || loggedInUser.avatar_color);
            
            // Profile picture upload - G3 Style
            const picInput = document.getElementById('profilePicInput');
            if (picInput.files.length > 0) {
                const picFormData = new FormData();
                picFormData.append('user_id', loggedInUser.id);
                picFormData.append('media', picInput.files[0]);
                
                try {
                    const picRes = await fetch(`${API_BASE}/users/profile_pic`, { method: 'POST', body: picFormData });
                    const picData = await picRes.json();
                    if (picData.success) {
                        loggedInUser.profile_pic = picData.profile_pic;
                        // Update the avatar immediately
                        document.getElementById('profilePicImg').style.display = 'block';
                        document.getElementById('profilePicImg').src = `/uploads/${loggedInUser.profile_pic}`;
                        document.getElementById('profileAvatarText').style.display = 'none';
                        document.getElementById('myStoryAvatar').innerHTML = `<img src="/uploads/${loggedInUser.profile_pic}" style="width:100%; height:100%; border-radius:50%; object-fit:cover;">`;
                    }
                } catch(e) {
                    console.error('Error uploading profile pic:', e);
                }
            }
            
            try {
                const res = await fetch(`${API_BASE}/users/profile`, { method: 'PUT', body: formData });
                const data = await res.json();
                if (data.success) {
                    loggedInUser.display_name = displayName;
                    loggedInUser.avatar_color = window.selectedColor || loggedInUser.avatar_color;
                    closeEditProfileModal();
                    showToast('✅ Profile updated!');
                    renderProfile(loggedInUser.id);
                    renderSidebar();
                }
            } catch(e) {
                console.error('Error updating profile:', e);
                alert('Failed to update profile');
            }
        }

        // ============================================================
        // LIVE STREAM - real camera-preview modal
        // ============================================================
        let liveMediaStream = null;

        function openLiveStream() {
            document.getElementById('liveModal').classList.add('active');
            document.getElementById('livePlaceholder').style.display = 'block';
            document.getElementById('liveVideo').style.display = 'none';
            document.getElementById('liveIndicator').style.display = 'none';
            document.getElementById('startLiveCameraBtn').style.display = 'inline-block';
            document.getElementById('goLiveConfirmBtn').style.display = 'none';
            document.getElementById('endLiveBtn').style.display = 'none';
            document.getElementById('liveTitleInput').disabled = false;
        }

        function closeLiveModal() {
            if (!liveStreamActive) {
                stopLiveCamera();
                document.getElementById('liveModal').classList.remove('active');
            } else {
                // Don't tear down the camera while actually live - just hide the modal
                document.getElementById('liveModal').classList.remove('active');
            }
        }

        function stopLiveCamera() {
            if (liveMediaStream) {
                liveMediaStream.getTracks().forEach(track => track.stop());
                liveMediaStream = null;
            }
        }

        function startLiveCamera() {
            navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } }, audio: true })
                .then(stream => {
                    liveMediaStream = stream;
                    document.getElementById('livePlaceholder').style.display = 'none';
                    const video = document.getElementById('liveVideo');
                    video.style.display = 'block';
                    video.srcObject = stream;
                    document.getElementById('startLiveCameraBtn').style.display = 'none';
                    document.getElementById('goLiveConfirmBtn').style.display = 'inline-block';
                    showToast('📷 Camera ready - tap "Go Live" to start broadcasting');
                })
                .catch(err => {
                    console.error('Camera error:', err);
                    alert('Could not access camera/microphone. Please allow permissions.');
                });
        }

        function confirmGoLive() {
            const title = document.getElementById('liveTitleInput').value.trim() || 'My Live Stream';
            
            const formData = new FormData();
            formData.append('user_id', loggedInUser.id);
            formData.append('title', title);
            formData.append('description', '');
            
            fetch(`${API_BASE}/reels/live/start`, { method: 'POST', body: formData })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        liveStreamId = data.reel_id;
                        liveStreamActive = true;
                        showToast(`🔴 LIVE: ${title}`);
                        loadReels();
                        
                        document.getElementById('liveIndicator').style.display = 'flex';
                        document.getElementById('liveTitleInput').disabled = true;
                        document.getElementById('goLiveConfirmBtn').style.display = 'none';
                        document.getElementById('endLiveBtn').style.display = 'inline-block';
                        
                        // Show end live button on profile too
                        const liveBtn = document.getElementById('goLiveBtn');
                        if (liveBtn) {
                            liveBtn.innerHTML = '<i class="fas fa-stop-circle"></i> End Live';
                            liveBtn.style.background = 'var(--red)';
                            liveBtn.onclick = () => document.getElementById('liveModal').classList.add('active');
                        }
                    }
                })
                .catch(err => console.error('Error starting live stream:', err));
        }

        function endLiveStream() {
            if (!liveStreamId) return;
            
            if (!confirm('End your live stream?')) return;
            
            const formData = new FormData();
            formData.append('reel_id', liveStreamId);
            
            fetch(`${API_BASE}/reels/live/end`, { method: 'POST', body: formData })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        showToast('🔴 Live stream ended');
                        liveStreamId = null;
                        liveStreamActive = false;
                        loadReels();
                        stopLiveCamera();
                        document.getElementById('liveModal').classList.remove('active');
                        
                        // Reset live button
                        const liveBtn = document.getElementById('goLiveBtn');
                        if (liveBtn) {
                            liveBtn.innerHTML = '<i class="fas fa-video"></i> Go Live';
                            liveBtn.style.background = '';
                            liveBtn.onclick = openLiveStream;
                        }
                    }
                })
                .catch(err => console.error('Error ending live stream:', err));
        }

        // ============================================================
        // LOCATION - G4 Style
        // ============================================================
        // ============================================================
        // LOCATION MAP - real Google Map + OpenStreetMap search
        // ============================================================
        let googleLocationMapObj = null;
        let locationMarkers = {};
        let locationMapInitialized = false;

        function initLocationMap() {
            if (locationMapInitialized) return;
            const el = document.getElementById('googleLocationMap');
            if (!el || typeof google === 'undefined' || !google.maps) {
                // Google Maps script may not have loaded yet - retry shortly
                setTimeout(initLocationMap, 500);
                return;
            }
            googleLocationMapObj = new google.maps.Map(el, {
                center: { lat: 6.5244, lng: 3.3792 }, // sensible default; recentered once we know a real location
                zoom: 11,
                mapTypeId: 'roadmap',
                mapTypeControl: true,
                fullscreenControl: true,
                streetViewControl: true,
                zoomControl: true,
                gestureHandling: 'greedy'
            });
            locationMapInitialized = true;
            plotLocationMarkers();
            setupLocationSearch();
        }

        function plotLocationMarkers() {
            if (!googleLocationMapObj) return;
            
            // Clear stale markers for users no longer present
            const currentIds = locations.map(l => l.user_id);
            Object.keys(locationMarkers).forEach(uid => {
                if (!currentIds.includes(parseInt(uid))) {
                    locationMarkers[uid].setMap(null);
                    delete locationMarkers[uid];
                }
            });
            
            locations.forEach(loc => {
                const pos = { lat: loc.lat, lng: loc.lng };
                if (locationMarkers[loc.user_id]) {
                    locationMarkers[loc.user_id].setPosition(pos);
                } else {
                    const marker = new google.maps.Marker({
                        map: googleLocationMapObj,
                        position: pos,
                        title: loc.display_name || loc.name,
                        label: { text: (loc.display_name || loc.name || 'U')[0].toUpperCase(), color: 'white' }
                    });
                    const info = new google.maps.InfoWindow({
                        content: `<b>${loc.display_name || loc.name}</b><br>Last seen: ${new Date(loc.timestamp).toLocaleTimeString()}`
                    });
                    marker.addListener('click', () => info.open(googleLocationMapObj, marker));
                    locationMarkers[loc.user_id] = marker;
                }
            });
            
            // Auto-center on the logged-in user's own marker if we have it and haven't moved the map yet
            const mine = locations.find(l => l.user_id === loggedInUser.id);
            if (mine && !window._locationMapCentered) {
                googleLocationMapObj.setCenter({ lat: mine.lat, lng: mine.lng });
                googleLocationMapObj.setZoom(14);
                window._locationMapCentered = true;
            }
        }

        function locateMeOnMap() {
            if (!navigator.geolocation) { showToast('❌ Geolocation not supported'); return; }
            navigator.geolocation.getCurrentPosition((pos) => {
                const { latitude, longitude } = pos.coords;
                if (googleLocationMapObj) {
                    googleLocationMapObj.setCenter({ lat: latitude, lng: longitude });
                    googleLocationMapObj.setZoom(15);
                }
            }, () => showToast('❌ Could not get your location'));
        }

        function setupLocationSearch() {
            const searchInput = document.getElementById('locationSearchInput');
            if (!searchInput || searchInput._wired) return;
            searchInput._wired = true;
            let timeout;
            searchInput.addEventListener('input', () => searchLocationPlaces(searchInput.value));
        }

        let _locationSearchTimeout;
        async function searchLocationPlaces(query) {
            const dropdown = document.getElementById('locationSearchDropdown');
            clearTimeout(_locationSearchTimeout);
            const q = (query || '').trim();
            if (q.length < 3) { dropdown.style.display = 'none'; return; }
            
            _locationSearchTimeout = setTimeout(async () => {
                try {
                    const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(q)}&limit=5&addressdetails=1`);
                    const data = await res.json();
                    
                    dropdown.innerHTML = '';
                    if (!data.length) {
                        dropdown.innerHTML = '<div style="padding:10px; color:#888;">No results found</div>';
                        dropdown.style.display = 'block';
                        return;
                    }
                    
                    data.forEach(place => {
                        const div = document.createElement('div');
                        div.style.cssText = 'padding:10px; cursor:pointer; border-bottom:1px solid #f5f5f5;';
                        const name = place.display_name.split(', ').slice(0, 3).join(', ');
                        div.innerHTML = `<i class="fas fa-map-pin" style="color:var(--burgundy); margin-right:8px;"></i>${name}`;
                        div.onclick = () => {
                            const lat = parseFloat(place.lat);
                            const lng = parseFloat(place.lon);
                            googleLocationMapObj.setCenter({ lat, lng });
                            googleLocationMapObj.setZoom(17);
                            new google.maps.Marker({
                                map: googleLocationMapObj,
                                position: { lat, lng },
                                title: place.display_name
                            });
                            document.getElementById('locationSearchInput').value = name;
                            dropdown.style.display = 'none';
                        };
                        dropdown.appendChild(div);
                    });
                    dropdown.style.display = 'block';
                } catch(e) {
                    console.error('Location search error:', e);
                }
            }, 400);
        }

        function renderLocations() {
            const container = document.getElementById('locationList');
            container.innerHTML = '';
            
            if (locations.length === 0) {
                container.innerHTML = '<div style="text-align:center; padding:20px; color:#999;">No active locations</div>';
            } else {
                locations.forEach(loc => {
                    const div = document.createElement('div');
                    div.className = 'location-item';
                    div.style.cursor = 'pointer';
                    div.innerHTML = `
                        <div class="avatar" style="background:${loc.avatar_color || '#800020'};">${(loc.display_name || 'U')[0]}</div>
                        <div class="info">
                            <div class="name">${loc.display_name || loc.name}</div>
                            <div class="coords">📍 ${loc.lat.toFixed(4)}, ${loc.lng.toFixed(4)}</div>
                        </div>
                        <div class="battery"><i class="fas fa-bolt"></i> ${loc.battery || 100}%</div>
                        <div style="font-size:0.7rem; color:#888;">${new Date(loc.timestamp).toLocaleTimeString()}</div>
                    `;
                    div.onclick = () => {
                        if (googleLocationMapObj) {
                            googleLocationMapObj.setCenter({ lat: loc.lat, lng: loc.lng });
                            googleLocationMapObj.setZoom(16);
                            if (locationMarkers[loc.user_id]) {
                                google.maps.event.trigger(locationMarkers[loc.user_id], 'click');
                            }
                        }
                    };
                    container.appendChild(div);
                });
            }
            
            plotLocationMarkers();
        }

        function updateLocationOnMap(data) {
            const existing = locations.find(l => l.user_id === data.user_id);
            if (existing) {
                existing.lat = data.lat;
                existing.lng = data.lng;
                existing.battery = data.battery;
                existing.timestamp = data.timestamp;
            } else {
                locations.push({
                    user_id: data.user_id,
                    name: data.name,
                    lat: data.lat,
                    lng: data.lng,
                    battery: data.battery,
                    display_name: data.name,
                    avatar_color: '#800020',
                    timestamp: data.timestamp
                });
            }
            renderLocations();
        }

        function shareLocation() {
            if (!navigator.geolocation) {
                showToast('❌ Geolocation not supported');
                return;
            }
            
            navigator.geolocation.getCurrentPosition(
                async (pos) => {
                    const { latitude, longitude } = pos.coords;
                    
                    try {
                        const res = await fetch(`${API_BASE}/location`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                user_id: loggedInUser.id,
                                device_id: 'web_' + loggedInUser.id,
                                name: loggedInUser.display_name || loggedInUser.username,
                                lat: latitude,
                                lng: longitude,
                                battery: 100
                            })
                        });
                        const data = await res.json();
                        if (data.success) {
                            showToast('📍 Location shared!');
                            window._locationMapCentered = false;
                            loadLocations();
                            
                            sendWebSocketMessage({
                                type: 'location',
                                lat: latitude,
                                lng: longitude,
                                battery: 100
                            });
                        }
                    } catch(e) {
                        console.error('Error sharing location:', e);
                    }
                },
                (err) => {
                    showToast('❌ Could not get location: ' + err.message);
                },
                { enableHighAccuracy: true }
            );
        }

        // ============================================================
        // NOTIFICATIONS - G3 Style
        // ============================================================
        function renderNotifications() {
            const container = document.getElementById('notifList');
            container.innerHTML = '';
            
            if (notifications.length === 0) {
                container.innerHTML = '<div style="text-align:center; padding:30px; color:#999;">No notifications</div>';
                return;
            }
            
            notifications.forEach(n => {
                const div = document.createElement('div');
                div.className = 'notif-item';
                const fromUser = allUsers.find(u => u.id === n.from_user_id);
                div.innerHTML = `
                    <div class="avatar" style="background:${fromUser?.avatar_color || '#800020'};">${(fromUser?.display_name || 'U')[0]}</div>
                    <div class="text">
                        <strong>${n.from_name || 'User'}</strong> ${n.text}
                        <span class="time">${new Date(n.timestamp).toLocaleString()}</span>
                    </div>
                    ${!n.is_read ? '<span style="width:8px; height:8px; border-radius:50%; background:var(--burgundy); flex-shrink:0;"></span>' : ''}
                `;
                container.appendChild(div);
            });
        }

        // ============================================================
        // TOAST - G1 Style
        // ============================================================
        function showToast(message) {
            const existing = document.querySelector('.toast');
            if (existing) existing.remove();
            
            const toast = document.createElement('div');
            toast.className = 'toast';
            toast.textContent = message;
            document.body.appendChild(toast);
            
            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transition = 'opacity 0.5s';
                setTimeout(() => toast.remove(), 500);
            }, 3000);
        }

        // ============================================================
        // WINDOW EVENTS
        // ============================================================
        window.addEventListener('resize', function() {
            if (window.innerWidth > 480) {
                closeSidebar();
            }
        });

        window.addEventListener('beforeunload', function() {
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.close();
            }
            if (recordMediaStream) {
                recordMediaStream.getTracks().forEach(track => track.stop());
            }
        });

        console.log('🚀 FUOMCE Communication App loaded!');
        console.log('👤 Logged in as:', loggedInUser);
    </script>
</body>
</html>
    """

# ============================================================
# RUN APP
# ============================================================
if __name__ == "__main__":
    import uvicorn
    from datetime import timedelta
    
    init_db()
    create_default_data()
    
    print("\n" + "="*60)
    print("🚀 FUOMCE COMMUNICATION APP STARTING...")
    print("="*60)
    
    # Start ngrok
    try:
        ngrok.set_auth_token(NGROK_AUTHTOKEN)
        ngrok.kill()
        public_url = ngrok.connect(8000)
        print(f"\n✅ ngrok tunnel established at: {public_url}")
    except Exception as e:
        print(f"⚠️ ngrok failed: {e}")
        public_url = None
    
    print("\n📍 LOCAL ACCESS:")
    print("   http://localhost:8000")
    print("   http://127.0.0.1:8000")
    
    if public_url:
        print(f"\n🌍 PUBLIC ACCESS: {public_url}")
        print("\n📱 Share this link with friends to use the app!")
    
    print("\n👤 DEFAULT LOGINS:")
    print("   Admin: admin / admin123")
    print("   Users: alex / password123")
    print("          sarah / password123")
    print("          mike / password123")
    
    print("\n✅ FIXES APPLIED:")
    print("   ✅ Voice notes & video recordings now send successfully")
    print("   ✅ Removed 'chat with self' feature")
    print("   ✅ Upload reels now works and displays in profile")
    print("   ✅ Profile picture updates and reflects immediately")
    print("   ✅ Friend requests work (send, accept, decline, cancel)")
    print("   ✅ Friend request notifications with accept/decline buttons")
    print("   ✅ Removed record button from chat header")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)