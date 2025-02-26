import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """
    Configuration management for the scheduling system.
    Loads sensitive values from environment variables.
    """
    
    @property
    def openai_api_key(self) -> Optional[str]:
        """Get OpenAI API key from environment variable."""
        return os.getenv('OPENAI_API_KEY')
    
    @property
    def anthropic_api_key(self) -> Optional[str]:
        """Get Anthropic API key from environment variable."""
        return os.getenv('ANTHROPIC_API_KEY')

    def validate(self) -> bool:
        """
        Validate that all required configuration is present.
        Returns True if configuration is valid, False otherwise.
        """
        required_vars = [
            ('OPENAI_API_KEY', self.openai_api_key),
            ('ANTHROPIC_API_KEY', self.anthropic_api_key),
        ]
        
        is_valid = True
        for var_name, value in required_vars:
            if not value:
                print(f"Missing required environment variable: {var_name}")
                is_valid = False
        
        return is_valid

# Global config instance
config = Config()

# Scheduling Configuration
STATIONS_PER_DAY = 12  # Number of parallel stations that can run per day
WORKERS_PER_STATION = 1  # Number of workers needed per station
MAX_WORKER_TASKS_PER_DAY = 2  # Maximum tasks a worker can do per day (can work 2 half-days)
TIME_SLOTS = ["AM", "PM"]  # Available time slots per day

# Shift timing configuration
SHIFT_HOURS = {
    "AM": {"start": "08:00", "end": "12:00"},
    "PM": {"start": "13:00", "end": "17:00"}
}

# Minimum time between shifts for same worker (hours)
MIN_SHIFT_GAP = 1.0

# Maximum shifts per worker per day
MAX_SHIFTS_PER_WORKER = 2 