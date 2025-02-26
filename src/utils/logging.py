import sys
import datetime

class Logger:
    def __init__(self, filename="log.txt"):
        self.terminal = sys.stdout
        # Reset the log file
        with open(filename, 'w') as f:
            f.write(f"=== Scheduling Run: {datetime.datetime.now()} ===\n\n")
        self.log = open(filename, 'a')

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

def setup_logging():
    """Setup logging to both console and file."""
    sys.stdout = Logger() 