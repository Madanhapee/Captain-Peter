from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import pickle
import os
from datetime import datetime, timedelta, timezone
from sklearn.preprocessing import LabelEncoder
from supabase import create_client, Client
import httpx  # Import httpx
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=4)
# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
# Supabase setup
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase URL and Key must be set as environment variables.")
# Initialize Supabase client.  Handle the httpx import error.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) # Removed http_client
class User(UserMixin):
    def __init__(self, user_id, username, password, role):
        self.user_id = user_id
        self.username = username
        self.password = password
        self.role = role
        print(f"User object created with role: {self.role}")
    def __repr__(self):
        return f'<User(username={self.username}, role={self.role})>'
    def check_password(self, password):
        return check_password_hash(self.password, password)
    def get_id(self):
        return str(self.user_id)
@login_manager.user_loader
def load_user(user_id):
    try:
        # Fetch user data from Supabase
        response = supabase.table('users').select('*').eq('user_id', user_id).execute()
        user_data = response.data[0] if response.data else None  # Access the first element
        if user_data:
            return User(
                user_data['user_id'],
                user_data['username'],
                user_data['password'],
                user_data['role']
            )
        return None
    except Exception as e:
        print(f"Error loading user: {e}")
        return None
@app.before_request
def before_request():
    session.permanent = True
    app.permanent_session_lifetime = app.config['PERMANENT_SESSION_LIFETIME']
    session.modified = True
    if current_user.is_authenticated and 'last_activity' in session:
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        last_activity = session['last_activity'].replace(tzinfo=timezone.utc)
        if now - last_activity > app.permanent_session_lifetime:
            logout_user()
            return redirect(url_for('login', message='Session timed out. Please log in again.'))
    session['last_activity'] = datetime.utcnow()
# Routes
@app.route('/')
def home():
    return render_template('home.html')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        print(f"Login attempt: username={username}, role={role}")
        try:
            # Fetch user data from Supabase
            response = supabase.table('users').select('*').eq('username', username).execute()
            user_data = response.data[0] if response.data else None
            print(f"User data from database: {user_data}")
            if user_data:
                db_password = user_data['password']
                db_role = user_data['role']
                print(f"DB role: {db_role}")
                password_match = check_password_hash(db_password, password)
                print(f"Password match: {password_match}")
                role_match = (role == db_role)
                print(f"Role match: {role_match}")
                if password_match and role_match:
                    user = User(user_data['user_id'], user_data['username'],
                                db_password, db_role)
                    login_user(user)
                    print(f"Login successful. User role: {user.role}")
                    if user.role == 'Admin':
                        print("Redirecting to admin_dashboard")
                        return redirect(url_for('admin_dashboard'))
                    elif user.role == 'Finance Officer':
                        print("Redirecting to finance_officer_dashboard")
                        return redirect(url_for('finance_officer_dashboard'))
                    elif user.role == 'Auditor':
                        print("Redirecting to auditor_dashboard")
                        return redirect(url_for('auditor_dashboard'))
                    else:
                        print("Login successful, but no specific role assigned.")
                        return render_template('home.html', message="Login successful, but no specific role assigned.")
                else:
                    print("Login failed: Invalid credentials or role.")
                    return render_template('Login1.html', error="Invalid credentials or role.")
            else:
                print("Login failed: User not found.")
                return render_template('Login1.html', error="Invalid credentials.")
        except Exception as e:
            print(f"Error during login: {e}")
            return render_template('Login1.html', error="Database error during login.")
    return render_template('Login1.html')
@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('last_activity', None)
    return redirect(url_for('home'))
# Admin functionalities
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'Admin':
        return jsonify({"msg": "Unauthorized"}), 403
    else:
        return render_template('admin.html')
@app.route('/add_user', methods=['GET', 'POST'])
@login_required
def add_user():
    if current_user.role != 'Admin':
        return jsonify({"msg": "Unauthorized"}), 403
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        if username and password and role:
            hashed_password = generate_password_hash(password)
            try:
                # Get next user ID
                response = supabase.table('users').select('user_id').order('user_id', desc=True).limit(1).execute()
                last_user_id = response.data[0]['user_id'] if response.data else 'USR0000'
                next_user_id_number = int(last_user_id[3:]) + 1
                user_id = f"USR{next_user_id_number:04d}"

                # Insert user into Supabase
                user_data = {
                    'user_id': user_id,
                    'username': username,
                    'password': hashed_password,
                    'role': role
                }
                response = supabase.table('users').insert(user_data).execute()
                if response.error:
                    raise Exception(response.error)
                return render_template('admin.html', message="User added successfully!")
            except Exception as e:
                print(f"Error adding user: {e}")
                return render_template('add user.html', error=f"Database error adding user: {e}")
        return render_template('add user.html', error="All fields are required.")
    return render_template('add user.html')
@app.route('/view_transactions', methods=['GET'])
def view_transactions():
    try:
        # Fetch transactions from Supabase
        response = supabase.table('transactions').select('*').execute()
        transactions_data = response.data
        # Convert to DataFrame
        transactions_df = pd.DataFrame(transactions_data)
        # Render template
        return render_template('view transaction.html', transactions=transactions_df.to_dict(orient='records'))
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        return jsonify({'error': "Database error fetching transactions."}), 500
@app.route('/add_transaction', methods=['GET', 'POST'])
@login_required
def add_transaction():
    if request.method == 'POST':
        account_id = request.form.get('account_id')
        transaction_date = request.form.get('transaction_date')
        amount = request.form.get('amount')
        transaction_type = request.form.get('transaction_type')
        transaction_purpose = request.form.get('transaction_purpose')
        if account_id and transaction_date and amount and transaction_type:
            try:
                # Get next transaction ID
                response = supabase.table('transactions').select('transaction_id').order('transaction_id', desc=True).limit(1).execute()
                last_transaction_id = response.data[0]['transaction_id'] if response.data else 'TX00000'
                next_transaction_id_number = int(last_transaction_id[2:]) + 1
                transaction_id = f"TX{next_transaction_id_number:05d}"
                # Insert transaction into Supabase
                transaction_data = {
                    'transaction_id': transaction_id,
                    'account_id': account_id,
                    'transaction_date': transaction_date,
                    'amount': amount,
                    'transaction_type': transaction_type,
                    'transaction_purpose': transaction_purpose
                }
                response = supabase.table('transactions').insert(transaction_data).execute()
                if response.error:
                    raise Exception(response.error)
                print("Transaction added successfully!", "success")
                return redirect(url_for('finance_officer_dashboard'))
            except Exception as e:
                print(f"Error adding transaction: {e}")
                return render_template('add transaction.html', error=f"Database error adding transaction: {e}")
        return render_template('add transaction.html', error="All fields are required.")
    return render_template('add transaction.html')
@app.route('/view_users')
@login_required
def view_users():
    if current_user.role != 'Admin':
        return jsonify({"msg": "Unauthorized"}), 403
    try:
        # Fetch users from Supabase
        response = supabase.table('users').select('user_id, username, role').execute()
        users_data = response.data
        # Convert to DataFrame
        users_df = pd.DataFrame(users_data)
        return render_template('view users1.html', users=users_df.to_dict(orient='records'))
    except Exception as e:
        print(f"Error fetching users: {e}")
        return jsonify({'error': "Database error fetching users."}), 500
@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        # Check if the current password is correct
        if check_password_hash(current_user.password, current_password):
            hashed_new_password = generate_password_hash(new_password)
            try:
                # Update password in Supabase
                response = supabase.table('users').update({'password': hashed_new_password}).eq('user_id', current_user.user_id).execute()
                if response.error:
                    raise Exception(response.error)
                print("Password changed successfully.", "success")
                return redirect(url_for('home'))
            except Exception as e:
                print(f"Error changing password: {e}")
                print("Database error changing password.", "danger")
                return render_template('change password.html')
        else:
            print("Current password is incorrect.", "danger")
            return render_template('change password.html')
    return render_template('change password.html')
# Finance Officer Dashboard
@app.route('/finance_officer_dashboard')
@login_required
def finance_officer_dashboard():
    if current_user.role != 'Finance Officer':
        return jsonify({"msg": "Unauthorized"}), 403
    return render_template('finance.html')
def fetch_transactions():
    response = supabase.table('transactions').select('*').execute()
    df = pd.DataFrame(response.data)
    return df
@app.route('/visualizations')
@login_required
def visualizations():
    if current_user.role not in ['Auditor', 'Finance Officer']:
        return jsonify({"msg": "Unauthorized"}), 403
    df = fetch_transactions()
    if df is None or df.empty:
        return render_template('transaction analysis.html', error="No transaction data available for visualization.")
    # Convert transaction_date to datetime format
    df['transaction_date'] = pd.to_datetime(df['transaction_date'], errors='coerce')
    # Drop rows with invalid dates (if any)
    df.dropna(subset=['transaction_date'], inplace=True)
    # Ensure amount is numeric
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    # Drop rows with NaN in amount
    df.dropna(subset=['amount'], inplace=True)
    # Summary statistics
    summary_stats = df[['amount']].describe()
    print(summary_stats)
    # Visualization 1: Transaction type distribution
    transaction_type_counts = df['transaction_type'].value_counts()
    plt.figure()
    sns.barplot(x=transaction_type_counts.index, y=transaction_type_counts.values)
    plt.title("Transaction Type Distribution")
    plt.xlabel("Transaction Type")
    plt.ylabel("Count")
    plt.savefig('static/transaction_type_distribution.png')
    plt.close()
    # Visualization 2: Monthly amount distribution by type
    df['month'] = df['transaction_date'].dt.strftime('%B')
    monthly_amount_by_type = df.groupby(['month', 'transaction_type'])['amount'].sum().unstack().fillna(0)
    # Ensure that monthly_amount_by_type contains numeric data
    if not monthly_amount_by_type.empty:
        plt.figure(figsize=(12, 6))
        monthly_amount_by_type.plot(kind='bar', stacked=True)
        plt.title("Monthly Amount Distribution by Transaction Type")
        plt.xlabel("Month")
        plt.ylabel("Total Amount")
        plt.xticks(rotation=45)
        plt.savefig('static/monthly_amount_by_type.png')
        plt.close()
    else:
        print("No data to plot for monthly amounts by type.")

    # Visualization 3: Countplot of account_id by transaction type
    plt.figure()
    sns.countplot(data=df, x='transaction_type', hue='account_id')
    plt.title("Count of Accounts by Transaction Type")
    plt.xlabel("Transaction Type")
    plt.ylabel("Count")
    plt.legend(title='Account ID')
    plt.savefig('static/countplot_account_by_type.png')
    plt.close()
    return render_template('transaction analysis.html', summary=summary_stats.to_html(classes='table table-striped'))
def detect_anomalies(df):
    # Load your model
    with open('final_model.pkl', 'rb') as file:
        model = pickle.load(file)
    # Encode transaction_type
    le = LabelEncoder()
    df['transaction_type_encoded'] = le.fit_transform(df['transaction_type'])
    model_df=pd.DataFrame(df['amount'])
    model_df['TransactionAmount']=model_df
    # Prepare data for prediction
    features = df[['transaction_type_encoded', 'amount']]
    # Predict anomalies
    df['anomaly'] = model.predict(pd.DataFrame(model_df['TransactionAmount']))
    # Extract anomalies
    anomalies = df[df['anomaly'] == -1]
    return anomalies
@app.route('/anomalies')
@login_required
def anomalies():
    if current_user.role not in ['Auditor', 'Finance Officer']:
        return jsonify({"msg": "Unauthorized"}), 403
    df = fetch_transactions()
    if df is None or df.empty:
        return render_template('anomaly_analysis.html', error="No transaction data available for analysis.")
    # Detect anomalies
    anomalies = detect_anomalies(df)
    return render_template('anomaly.html', anomalies=anomalies)
# Auditor Dashboard
@app.route('/auditor_dashboard')
@login_required
def auditor_dashboard():
    if current_user.role != 'Auditor':
        return jsonify({"msg": "Unauthorized"}), 403
    return render_template('Auditor.html')
if __name__ == '__main__':
    app.run()
