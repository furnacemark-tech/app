import sys
from pathlib import Path

# Add backend directory to Python path so 'from database import db' works
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
