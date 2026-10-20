"""
Medflow Command Center
SECRET_KEY: it is loaded from the environment, like MONGODB_URL

We will not be committing a real secret key here if this were a real project being pushed to production 
(this would not be a secure place to put it).
"""
import os
from datetime import timedelta, datetime, timezone

import bcrypt
import jwt

from app.config import settings

# security constants and helper functions for password hashing and JWT token management
SECRET_KEY = settings.secret_key

# define our algorithm for signing the JWT (JSON Web Tokens) tokens
# there are many algorithms to choose from, we will be choosing HS256 (this is a common choice for symmetric signing)
ALGORITHM = "HS256"

# expiration time for access tokens (in minutes)
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# we need two different functions for password hashing and verification to make sure 
# we are never storing plaintext passwords in the database. Instead, we store the hashed password, which is
# a one-way transformation that cannot be easily reversed.
# takes a plantext password as input, uses bcrypt to hash it, and returns the hashed password as a string
def hash_password(plain : str)-> str:
    hashed = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")

# this takes a hashed password and plain password as input, then checks to see if the plaintext 
# password matches the hashed password
def verify_password(hashed : str, plain : str)-> bool:
    return bcrypt.checkpw(
        password = plain.encode("utf-8"),
        hashed_password= hashed.encode("utf-8")
    )


# creation of the JWT
# this function creates a JWT access token with the provided data and an optional expiration time
def create_access_token(data : dict, expires_delta : timedelta | None = None)-> str:
    # copy of the input data dictionary, used to create the JWT payload
    to_encode = data.copy()

    # check if an expiration time was provided
    # if not, we can use the default time expiration defined by ACCESS_TOKEN_EXPIRED_MINUTES
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm = ALGORITHM)

# this function decodes our access token and returns the payload as a dictionary
def decode_access_token(token : str)->dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])