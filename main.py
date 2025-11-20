import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson.objectid import ObjectId

from database import db, create_document, get_documents
from schemas import User as UserSchema, Product as ProductSchema, Cart as CartSchema, CartItem as CartItemSchema, Order as OrderSchema, OrderItem as OrderItemSchema

app = FastAPI(title="E-commerce SaaS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utilities

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def serialize(doc):
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc


# Auth models (simplified email+password) - demo only
class SignUpRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class SignInRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    user_id: str
    name: str
    email: EmailStr
    token: str


# Routes
@app.get("/")
def root():
    return {"message": "E-commerce SaaS API running"}

@app.get("/test")
def test_database():
    resp = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            resp["database"] = "✅ Available"
            resp["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            resp["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
            try:
                resp["collections"] = db.list_collection_names()[:10]
                resp["database"] = "✅ Connected & Working"
                resp["connection_status"] = "Connected"
            except Exception as e:
                resp["database"] = f"⚠️ Connected but error: {str(e)[:80]}"
        else:
            resp["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        resp["database"] = f"❌ Error: {str(e)[:80]}"
    return resp


# Auth endpoints (simple, not production ready: stores password hash naive for demo)
from hashlib import sha256

def hash_password(pw: str) -> str:
    return sha256((pw + os.getenv("AUTH_SALT", "flames_saas")).encode()).hexdigest()

@app.post("/auth/signup", response_model=AuthResponse)
def signup(payload: SignUpRequest):
    existing = db["user"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = UserSchema(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_active=True,
        role="user"
    )
    user_id = create_document("user", user)
    token = hash_password(payload.email + ":" + payload.password)
    return AuthResponse(user_id=user_id, name=payload.name, email=payload.email, token=token)

@app.post("/auth/signin", response_model=AuthResponse)
def signin(payload: SignInRequest):
    user = db["user"].find_one({"email": payload.email})
    if not user or user.get("password_hash") != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = hash_password(payload.email + ":" + payload.password)
    return AuthResponse(user_id=str(user["_id"]), name=user["name"], email=user["email"], token=token)


# Products
@app.post("/products")
def create_product(product: ProductSchema):
    pid = create_document("product", product)
    return {"id": pid}

@app.get("/products")
def list_products():
    items = [serialize(p) for p in db["product"].find().limit(100)]
    return items

# Cart
class AddToCartRequest(BaseModel):
    user_id: str
    product_id: str
    quantity: int = 1

@app.post("/cart/add")
def add_to_cart(payload: AddToCartRequest):
    user_oid = oid(payload.user_id)
    product_oid = oid(payload.product_id)
    product = db["product"].find_one({"_id": product_oid})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    cart = db["cart"].find_one({"user_id": payload.user_id})
    if not cart:
        cart_doc = CartSchema(user_id=payload.user_id, items=[{"product_id": payload.product_id, "quantity": payload.quantity}])
        create_document("cart", cart_doc)
    else:
        # update quantity or add new item
        updated = False
        for item in cart.get("items", []):
            if item["product_id"] == payload.product_id:
                item["quantity"] += payload.quantity
                updated = True
        if not updated:
            cart.setdefault("items", []).append({"product_id": payload.product_id, "quantity": payload.quantity})
        db["cart"].update_one({"_id": cart["_id"]}, {"$set": {"items": cart["items"]}})
    return {"ok": True}

@app.get("/cart/{user_id}")
def get_cart(user_id: str):
    cart = db["cart"].find_one({"user_id": user_id})
    if not cart:
        return {"items": [], "total": 0}
    # enrich with product info
    items = []
    total = 0.0
    for item in cart.get("items", []):
        prod = db["product"].find_one({"_id": oid(item["product_id"])})
        if prod:
            subtotal = prod["price"] * item["quantity"]
            total += subtotal
            items.append({
                "product_id": item["product_id"],
                "title": prod["title"],
                "price": prod["price"],
                "quantity": item["quantity"],
                "image_url": prod.get("image_url"),
                "subtotal": subtotal
            })
    return {"items": items, "total": round(total, 2)}

# Checkout (mock payment provider)
class CheckoutRequest(BaseModel):
    user_id: str

@app.post("/checkout")
def checkout(payload: CheckoutRequest):
    cart = db["cart"].find_one({"user_id": payload.user_id})
    if not cart or not cart.get("items"):
        raise HTTPException(status_code=400, detail="Cart is empty")
    # build order items
    items: List[OrderItemSchema] = []
    amount = 0.0
    for item in cart["items"]:
        prod = db["product"].find_one({"_id": oid(item["product_id"])})
        if not prod:
            raise HTTPException(status_code=400, detail="Invalid product in cart")
        subtotal = prod["price"] * item["quantity"]
        amount += subtotal
        items.append(OrderItemSchema(
            product_id=str(prod["_id"]),
            title=prod["title"],
            price=prod["price"],
            quantity=item["quantity"],
            subtotal=subtotal,
        ))
    amount = round(amount, 2)

    # mock payment success and create order
    payment_ref = "PAY-" + os.urandom(4).hex().upper()
    order = OrderSchema(
        user_id=payload.user_id,
        items=[i.model_dump() for i in items],
        amount=amount,
        currency="usd",
        status="paid",
        payment_ref=payment_ref,
    )
    order_id = create_document("order", order)

    # clear cart
    db["cart"].update_one({"user_id": payload.user_id}, {"$set": {"items": []}})

    return {"order_id": order_id, "amount": amount, "currency": "usd", "payment_ref": payment_ref}
