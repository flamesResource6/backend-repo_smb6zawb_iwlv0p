"""
Database Schemas for the E-commerce SaaS

Each Pydantic model corresponds to a MongoDB collection.
Collection name is the lowercase of the class name.

- User -> "user"
- Product -> "product"
- Cart -> "cart"
- Order -> "order"
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List

class User(BaseModel):
    """Users collection schema"""
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="BCrypt password hash")
    is_active: bool = Field(True, description="Whether user is active")
    role: str = Field("user", description="Role: user or admin")

class Product(BaseModel):
    """Products collection schema"""
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    image_url: Optional[str] = Field(None, description="Primary image URL")
    category: Optional[str] = Field(None, description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

class CartItem(BaseModel):
    product_id: str = Field(..., description="ID of the product")
    quantity: int = Field(1, ge=1, description="Quantity of the product")

class Cart(BaseModel):
    user_id: str = Field(..., description="Owner user id")
    items: List[CartItem] = Field(default_factory=list, description="List of cart items")

class OrderItem(BaseModel):
    product_id: str
    title: str
    price: float
    quantity: int
    subtotal: float

class Order(BaseModel):
    user_id: str
    items: List[OrderItem]
    amount: float
    currency: str = Field("usd")
    status: str = Field("pending", description="pending|paid|failed|refunded")
    payment_ref: Optional[str] = Field(None, description="Reference from payment provider")
