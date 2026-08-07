from flask import Blueprint
auth_bp = Blueprint('auth', __name__)
from app.auth import routes
from app.auth.routes import init_oauth, google, oauth
