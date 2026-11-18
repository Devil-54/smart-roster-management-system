import os
from flask import Flask
from config import config_by_name
from app.extensions import db

def create_app(config_name='default'):
    if config_name not in config_by_name:
        raise ValueError(f"Unknown application configuration: {config_name}")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])
    if config_name == 'production':
        app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
        if (
            not app.config.get('SECRET_KEY')
            or len(app.config['SECRET_KEY']) < 32
            or app.config['SECRET_KEY'].lower().startswith(
                ('replace-', 'changeme', 'your-')
            )
        ):
            raise RuntimeError(
                'Set SECRET_KEY to a strong, private value before using production configuration.'
            )

    # Ensure instance and exports directories exist
    os.makedirs(app.config.get('EXPORTS_DIR', 'exports'), exist_ok=True)

    # Initialize extensions
    db.init_app(app)

    # Register Blueprints
    from app.routes.dashboard import dashboard_bp
    from app.routes.employees import employees_bp
    from app.routes.operations import operations_bp
    from app.routes.leaves import leaves_bp
    from app.routes.roster import roster_bp
    from app.routes.api import api_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(employees_bp, url_prefix='/employees')
    app.register_blueprint(operations_bp, url_prefix='/operations')
    app.register_blueprint(leaves_bp, url_prefix='/leaves')
    app.register_blueprint(roster_bp, url_prefix='/roster')
    app.register_blueprint(api_bp, url_prefix='/api')

    # Register shell context
    @app.shell_context_processor
    def make_shell_context():
        from app import models
        return {'db': db, 'models': models}

    # Custom template filters
    @app.template_filter('format_date')
    def format_date_filter(val, fmt='%b %d, %Y'):
        if not val:
            return ''
        if isinstance(val, str):
            from datetime import datetime
            try:
                val = datetime.strptime(val, '%Y-%m-%d').date()
            except Exception:
                return val
        return val.strftime(fmt)

    return app
