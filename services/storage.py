import sqlite3
import json
import uuid
from datetime import datetime



class StorageService:
    def __init__(self, db_path='cv_analyzer.db'):
        self.conn = sqlite3.connect(db_path)
        self.create_tables()

    def create_tables(self):
        with self.conn:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    is_premium BOOLEAN DEFAULT FALSE,
                    cv_count INTEGER DEFAULT 0,
                    last_activity TIMESTAMP
                )
            ''')
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS cvs (
                    cv_id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    file_id TEXT,
                    analyzed_data TEXT,
                    model TEXT,
                    rating INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS job_positions (
                    position_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_name TEXT UNIQUE
                )
            ''')
            
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS cv_job_positions (
                    cv_id TEXT,
                    position_id INTEGER,
                    FOREIGN KEY (cv_id) REFERENCES cvs (cv_id),
                    FOREIGN KEY (position_id) REFERENCES job_positions (position_id),
                    PRIMARY KEY (cv_id, position_id)
                )
            ''')

    def save_user(self, user_id, username):
        with self.conn:
            self.conn.execute('''
                INSERT OR REPLACE INTO users (user_id, username, last_activity)
                VALUES (?, ?, ?)
            ''', (user_id, username, datetime.now()))

    def get_user(self, user_id):
        with self.conn:
            cursor = self.conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user_data = cursor.fetchone()
            if user_data:
                return {
                    'user_id': user_data[0],
                    'username': user_data[1],
                    'is_premium': user_data[2],
                    'cv_count': user_data[3],
                    'last_activity': user_data[4]
                }
            return None

    def save_cv(self, cv_data):
        cv_id = str(uuid.uuid4())
        with self.conn:
            # Save or update user data
            self.save_user(cv_data['user_id'], cv_data.get('username', ''))
            
            # Increment user's CV count
            self.conn.execute('UPDATE users SET cv_count = cv_count + 1 WHERE user_id = ?', (cv_data['user_id'],))
            
            # Save CV data
            self.conn.execute('''
                INSERT INTO cvs (cv_id, user_id, file_id, analyzed_data, model, rating)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (cv_id, cv_data['user_id'], cv_data['file_id'], json.dumps(cv_data['analyzed_data']), cv_data['model'], cv_data['rating']))
        return cv_id

    def get_cv(self, cv_id):
        with self.conn:
            cursor = self.conn.execute('SELECT * FROM cvs WHERE cv_id = ?', (cv_id,))
            cv_data = cursor.fetchone()
            if cv_data:
                return {
                    'cv_id': cv_data[0],
                    'user_id': cv_data[1],
                    'file_id': cv_data[2],
                    'analyzed_data': json.loads(cv_data[3]),
                    'model': cv_data[4],
                    'rating': cv_data[5],
                    'created_at': cv_data[6]
                }
            return None

    def update_cv_rating(self, cv_id, rating):
        with self.conn:
            self.conn.execute('UPDATE cvs SET rating = ? WHERE cv_id = ?', (rating, cv_id))

    def get_all_cvs(self):
        with self.conn:
            cursor = self.conn.execute('SELECT * FROM cvs')
            return [dict(zip(['cv_id', 'user_id', 'file_id', 'analyzed_data', 'model', 'rating', 'created_at'], row)) for row in cursor.fetchall()]

    def increment_user_cv_count(self, user_id):
        with self.conn:
            self.conn.execute('UPDATE users SET cv_count = cv_count + 1 WHERE user_id = ?', (user_id,))

    def get_service_quality_metrics(self):
        with self.conn:
            cursor = self.conn.execute('SELECT rating FROM cvs WHERE rating IS NOT NULL')
            ratings = [row[0] for row in cursor.fetchall()]

        total_ratings = len(ratings)
        rating_sum = sum(ratings)
        rating_distribution = {i: ratings.count(i) for i in range(1, 6)}

        if total_ratings > 0:
            average_rating = rating_sum / total_ratings
        else:
            average_rating = 0

        return {
            "total_ratings": total_ratings,
            "average_rating": average_rating,
            "rating_distribution": rating_distribution
        }

    def print_database_contents(self):
        print("Users table:")
        with self.conn:
            cursor = self.conn.execute("SELECT * FROM users")
            for row in cursor.fetchall():
                print(row)

        print("\nCVs table:")
        with self.conn:
            cursor = self.conn.execute("SELECT * FROM cvs")
            for row in cursor.fetchall():
                print(row)

    def add_last_activity_column(self):
        try:
            with self.conn:
                self.conn.execute("ALTER TABLE users ADD COLUMN last_activity TIMESTAMP")
            print("Added last_activity column to users table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("last_activity column already exists")
            else:
                raise

    def save_job_position(self, position_name):
        with self.conn:
            cursor = self.conn.execute('''
                INSERT OR IGNORE INTO job_positions (position_name) VALUES (?)
            ''', (position_name,))
            position_id = cursor.lastrowid or self.conn.execute(
                'SELECT position_id FROM job_positions WHERE position_name = ?', (position_name,)
            ).fetchone()[0]
            print(f"Saved job position: {position_name} with ID: {position_id}")  # Add this line for debugging
            return position_id

    def save_cv_job_positions(self, cv_id, position_names):
        print(f"Saving job positions for CV {cv_id}: {position_names}")  # Add this line for debugging
        with self.conn:
            for position_name in position_names:
                position_id = self.save_job_position(position_name)
                self.conn.execute('''
                    INSERT OR IGNORE INTO cv_job_positions (cv_id, position_id) VALUES (?, ?)
                ''', (cv_id, position_id))
                print(f"Saved CV-job position relation: CV {cv_id}, Position {position_id}")  # Add this line for debugging

    def get_cv_job_positions(self, cv_id):
        with self.conn:
            cursor = self.conn.execute('''
                SELECT jp.position_name
                FROM cv_job_positions cvjp
                JOIN job_positions jp ON cvjp.position_id = jp.position_id
                WHERE cvjp.cv_id = ?
            ''', (cv_id,))
            return [row[0] for row in cursor.fetchall()]

    def get_similar_cvs(self, job_position, limit=5):
        with self.conn:
            cursor = self.conn.execute('''
                SELECT c.cv_id, c.analyzed_data, COUNT(DISTINCT cvjp.position_id) as match_count
                FROM cvs c
                JOIN cv_job_positions cvjp ON c.cv_id = cvjp.cv_id
                JOIN job_positions jp ON cvjp.position_id = jp.position_id
                WHERE jp.position_name = ?
                GROUP BY c.cv_id
                ORDER BY match_count DESC
                LIMIT ?
            ''', (job_position, limit))
            return [{'cv_id': row[0], 'analyzed_data': json.loads(row[1]), 'match_count': row[2]} for row in cursor.fetchall()]
