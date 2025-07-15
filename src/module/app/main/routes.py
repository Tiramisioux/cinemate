from flask import Blueprint, render_template

main_routes = Blueprint('main', __name__)

@main_routes.route('/')
def index():
    return render_template('template.html')
