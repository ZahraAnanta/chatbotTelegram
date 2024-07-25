import os
import google.generativeai as genai
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from datetime import datetime, timedelta
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackContext, filters, ContextTypes, ConversationHandler
)
import mysql.connector
from mysql.connector import Connect, Error
from sqlalchemy import create_engine
from io import BytesIO
import pandas as pd
import seaborn as sns
import logging
from dateutil.relativedelta import relativedelta

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

API_KEY = os.getenv('GOOGLE_API_KEY')
TELEGRAM_API_KEY = os.getenv('TELEGRAM_API_KEY')
MYSQL_HOST = os.getenv('MYSQL_HOST')
MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

# Configure the Gemini API
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel(model_name='gemini-pro')
chat = model.start_chat(history=[])
instruction = "In this chat, respond as if you're explaining things to a five-year-old child"

# Define a constant for the maximum message length
MAX_MESSAGE_LENGTH = 4096

# Define SQLAlchemy engines
engine_a = create_engine('mysql+pymysql://root:jejeluv@localhost:3306/ptpn_database')
engine_b = create_engine('mysql+pymysql://uapp:uapppass@192.168.200.52:3306/pks')

# Establish MySQL database connection
def get_db_connection():
    try:
        return mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
    except Error as e:
        logging.error(f"Error connecting to MySQL database: {e}")
        return None

# Function to handle the /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Hello! Ask me anything.')

# Function to handle messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = update.message.text
    if question.strip() != '':
        response = chat.send_message(question)
        await update.message.reply_text(response.text)
    else:
        await update.message.reply_text('Please ask a question.')

# Function to handle the /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    response_text = (
        "Here are the commands you can use:\n\n"
        "/start - Memulai bot\n\n"
        "/help - Menampilkan pesan ini\n\n"
        "/tampilkan_avg_berat_per_supplier - Menampilkan berat berdasarkan supplier \n\n"
        "/info - Menampilkan info keseluruhan site \n\n"
        "/detail - Menampilkan berat bersih pada site tertentu untuk kurun waktu Day to date, Month to date, Year to date \n\n"
    )
    await update.message.reply_text(response_text)

# Function to get average weight per supplier
async def get_avg_weight_per_supplier(supplier_name: str) -> list:
    db_conn = get_db_connection()
    if db_conn is None:
        return ["Failed to connect to the database."]

    try:
        with db_conn.cursor(dictionary=True) as cursor:
            query = """
                SELECT supplier_ffb.SUPPLIERNAME,
                       supplier_ffb.KOMODITAS,
                       AVG(wbticket.BERATBERSIH) as avg_berat_bersih
                FROM wbticket
                JOIN supplier_ffb ON wbticket.SUPPLIERCODE = supplier_ffb.SUPPLIERCODE
                WHERE supplier_ffb.SUPPLIERNAME = %s
                GROUP BY supplier_ffb.SUPPLIERNAME, supplier_ffb.KOMODITAS
            """
            cursor.execute(query, (supplier_name,))
            rows = cursor.fetchall()

            if rows:
                response_texts = []
                current_text = "Rata-rata Berat per Supplier:\n\n"
                for row in rows:
                    entry = (f"Supplier: {row['SUPPLIERNAME']}\n"
                             f"Komoditas: {row['KOMODITAS']}\n"
                             f"Rata-rata Berat Bersih\t: {row['avg_berat_bersih']} t\n\n")
                    if len(current_text) + len(entry) > 4096:
                        response_texts.append(current_text)
                        current_text = entry
                    else:
                        current_text += entry
                response_texts.append(current_text)
            else:
                response_texts = ["Tidak ada data yang ditemukan untuk supplier tersebut."]
    except Error as e:
        response_texts = [f"Error fetching average weight per supplier: {e}"]
    finally:
        if db_conn.is_connected():
            db_conn.close()

    return response_texts

async def tampilkan_avg_berat_per_supplier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        supplier_name = ' '.join(context.args)
        response_texts = await get_avg_weight_per_supplier(supplier_name)
    else:
        response_texts = ["Silakan berikan nama supplier setelah perintah. Contoh: /tampilkan_avg_berat_per_supplier NamaSupplier"]

    for response_text in response_texts:
        await update.message.reply_text(response_text)


#Function to get weight per storage
async def get_total_weight_per_storage(storage=None, tanggal=None) -> str:
    db_conn = get_db_connection()
    if db_conn is None:
        return "Failed to connect to the database."

    try:
        with db_conn.cursor(dictionary=True) as cursor:
            if tanggal:
                target_date = datetime.strptime(tanggal, '%Y-%m-%d')
            else:
                target_date = datetime.now()

            this_month = target_date.strftime('%Y-%m')
            this_year = target_date.year

            query = """
                SELECT STORAGE,
                       SUM(CASE WHEN DATE(TGLMASUK) = %(target_date)s THEN BERATBERSIH ELSE 0 END) as total_berat_bersih_hari_ini,
                       SUM(CASE WHEN DATE_FORMAT(TGLMASUK, '%Y-%m') = %(this_month)s THEN BERATBERSIH ELSE 0 END) as total_berat_bersih_bulan_ini,
                       SUM(CASE WHEN YEAR(TGLMASUK) = %(this_year)s THEN BERATBERSIH ELSE 0 END) as total_berat_bersih_tahun_ini
                FROM wbticket
                WHERE 1=1
            """
            params = {'target_date': target_date.date(), 'this_month': this_month, 'this_year': this_year}
            if storage:
                query += " AND STORAGE = %(storage)s"
                params['storage'] = storage

            query += " GROUP BY STORAGE"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            if rows:
                response_text = ""
                for row in rows:
                    response_text += (f"Nama Gudang: {row['STORAGE']}\n"
                                      f"Total Berat Bersih Hari Ini\t: {row['total_berat_bersih_hari_ini']} t\n"
                                      f"Total Berat Bersih Bulan Ini\t: {row['total_berat_bersih_bulan_ini']} t\n"
                                      f"Total Berat Bersih Tahun Ini\t: {row['total_berat_bersih_tahun_ini']} t\n\n")
            else:
                response_text = "Tidak ada data yang ditemukan untuk kriteria yang diberikan."

    except Error as e:
        response_text = f"Error fetching total weight per storage: {e}"
    finally:
        if db_conn.is_connected():
            db_conn.close()

    return response_text

# Fungsi untuk menampilkan total berat per storage
async def tampilkan_total_berat_per_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = update.message.text.split()[1:]  # Memisahkan argumen dari teks pesan
    storage = None
    tanggal = None
    
    for arg in args:
        if arg.startswith('storage:'):
            storage = arg.split(':')[1]
        elif arg.startswith('tanggal:'):
            tanggal = arg.split(':')[1]

    response_text = await get_total_weight_per_storage(storage=storage, tanggal=tanggal)
    await update.message.reply_text(response_text)

def split_message(text: str, max_length: int) -> list:
    """Split the message into chunks of a specified maximum length."""
    return [text[i:i+max_length] for i in range(0, len(text), max_length)]


#adam
def fetch_data_from_db(query):
    """
    Fetch data from the database and return it as a DataFrame.
    """
    connection = get_db_connection()
    if connection:
        try:
            df = pd.read_sql(query, connection)
            return df
        except Error as e:
            print(f"Error reading data from MySQL table: {e}")
        finally:
            if connection.is_connected():
                connection.close()
    return pd.DataFrame()

def get_data(site_id, tanggal, df):
    """
    Get data for a specific site and date from the DataFrame.
    """
    today = datetime.strptime(tanggal, '%Y-%m-%d')
    yesterday = today - timedelta(days=1)
    first_day_of_month = today.replace(day=1)
    first_day_of_year = today.replace(month=1, day=1)

    df_today = df[df['POSTINGDT'] == today.strftime('%Y-%m-%d')]
    df_month = df[df['POSTINGDT'] >= first_day_of_month.strftime('%Y-%m-%d')]
    df_year = df[df['POSTINGDT'] >= first_day_of_year.strftime('%Y-%m-%d')]

    today_weight = df_today.groupby('SUPPLIERCODE')['BERATBERSIH'].sum()
    month_weight = df_month.groupby('SUPPLIERCODE')['BERATBERSIH'].sum()
    year_weight = df_year.groupby('SUPPLIERCODE')['BERATBERSIH'].sum()

    total_today_weight = df_today['BERATBERSIH'].sum()
    total_month_weight = df_month['BERATBERSIH'].sum()
    total_year_weight = df_year['BERATBERSIH'].sum()

    return today_weight, month_weight, year_weight, total_today_weight, total_month_weight, total_year_weight

def display_info(site_id, tanggal, df):
    """
    Display information for a specific site and date.
    """
    today_weight, month_weight, year_weight, total_today_weight, total_month_weight, total_year_weight = get_data(site_id, tanggal, df)

    info = f"Info Pabrik (SITE_ID: {site_id})\n\n"
    for supplier in today_weight.index:
        info += (f"Asal Kebun                               : {supplier}\n"
                 f"Berat Diterima pada Hari ini             : {today_weight[supplier]} kg\n"
                 f"Berat Diterima pada Bulan sampai hari ini: {month_weight[supplier]} kg\n"
                 f"Berat Diterima pada Tahun sampai hari ini: {year_weight[supplier]} kg\n\n")

        info += (f"TOTAL Berat Bersih pada {site_id}:\n"
                 f"Berat Diterima Hari ini                  : {total_today_weight} kg\n"
                 f"Berat Diterima pada Bulan sampai hari ini: {total_month_weight} kg\n"
                 f"Berat Diterima pada Tahun sampai hari ini: {total_year_weight} kg")

    return info

# Function to handle the /info command
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Example query to fetch data, modify as needed
    query = "SELECT * FROM wbticket"
    df = fetch_data_from_db(query)

    site_id = context.args[0] if context.args else 'default_site_id'
    tanggal = context.args[1] if context.args else datetime.now().strftime('%Y-%m-%d')

    info_message = display_info(site_id, tanggal, df)
    await update.message.reply_text(info_message)


async def get_data_site_tanggal(site_id, tanggal) -> str:
    db_conn = get_db_connection()
    if db_conn is None:
        return "Failed to connect to the database."

    try:
        # Query to get data from Database A (ptpn_database)
        query_a = "SELECT SITE_ID, site_name, SUPPLIERCODEGROUP, SUPPLIERNAME FROM ticket WHERE SITE_ID = %s"
        df_a = pd.read_sql(query_a, engine_a, params=(site_id, ))

        # Check if site_name was found
        if df_a.empty:
            return "No site found with the provided SITE_ID."

        site_name = df_a.iloc[0]['site_name']
        
        # Create a dictionary to map SUPPLIERCODEGROUP to SUPPLIERNAME
        supplier_map = df_a.set_index('SUPPLIERCODEGROUP')['SUPPLIERNAME'].to_dict()

        with db_conn.cursor(dictionary=True) as cursor:
            # Query for today's data
            query_today = """
                SELECT JENISMUATAN, SITE_ID, SUPPLIERCODEGROUP, SUM(BERATBERSIH - GRD_RCUTKGFIX) AS NETTO
                FROM wbticket
                WHERE POSTINGDT = %s AND SITE_ID = %s AND JENISMUATAN = '31000010'
                GROUP BY JENISMUATAN, SITE_ID, SUPPLIERCODEGROUP
            """
            cursor.execute(query_today, (tanggal + ' 00:00:00', site_id))
            data_today = cursor.fetchall()

            # Query for month-to-date data
            start_of_month = tanggal[:8] + '01'
            query_month = """
                SELECT JENISMUATAN, SITE_ID, SUPPLIERCODEGROUP, SUM(BERATBERSIH - GRD_RCUTKGFIX) AS NETTO
                FROM wbticket
                WHERE POSTINGDT BETWEEN %s AND %s AND SITE_ID = %s AND JENISMUATAN = '31000010'
                GROUP BY JENISMUATAN, SITE_ID, SUPPLIERCODEGROUP
            """
            cursor.execute(query_month, (start_of_month + ' 00:00:00', tanggal + ' 23:59:59', site_id))
            data_month = cursor.fetchall()

            # Query for year-to-date data
            start_of_year = tanggal[:5] + '01-01'
            query_year = """
                SELECT JENISMUATAN, SITE_ID, SUPPLIERCODEGROUP, SUM(BERATBERSIH - GRD_RCUTKGFIX) AS NETTO
                FROM wbticket
                WHERE POSTINGDT BETWEEN %s AND %s AND SITE_ID = %s AND JENISMUATAN = '31000010'
                GROUP BY JENISMUATAN, SITE_ID, SUPPLIERCODEGROUP
            """
            cursor.execute(query_year, (start_of_year + ' 00:00:00', tanggal + ' 23:59:59', site_id))
            data_year = cursor.fetchall()

        response_text = f"Data for {site_name} on {tanggal}:\n\n"
        index = 1

        # Initialize total NETTO values
        total_netto_today = 0
        total_netto_month = 0
        total_netto_year = 0

        # Process today's data
        if data_today:
            response_text += "Data hari ini:\n"
            for row in data_today:
                supplier_name = supplier_map.get(row['SUPPLIERCODEGROUP'], 'Unknown Supplier')
                netto = row['NETTO']
                total_netto_today += netto
                response_text += (f" - Kode Muatan\t\t\t: {row['JENISMUATAN']}, \n"
                                  f"   Kode Supplier\t: {row['SUPPLIERCODEGROUP']}, \n"
                                  f"   Nama Supplier\t: {supplier_name}, \n"
                                  f"   NETTO\t\t\t\t: {netto:,.0f} kg \n\n")
                index += 1
            response_text += f"**Total NETTO hari ini: {total_netto_today:,.0f} kg**\n"
        else:
            response_text += "No data found for today.\n"

        # Process month-to-date data
        if data_month:
            response_text += "\nData pada Bulan:\n"
            for row in data_month:
                supplier_name = supplier_map.get(row['SUPPLIERCODEGROUP'], 'Unknown Supplier')
                netto = row['NETTO']
                total_netto_month += netto
                response_text += (f" - Kode Muatan\t\t\t: {row['JENISMUATAN']}, \n"
                                  f"   Kode Supplier\t: {row['SUPPLIERCODEGROUP']}, \n"
                                  f"   Nama Supplier\t: {supplier_name}, \n"
                                  f"   NETTO\t\t\t\t: {netto:,.0f} kg \n\n")
                index += 1
            response_text += f"**Total NETTO bulan ini: {total_netto_month:,.0f} kg**\n"
        else:
            response_text += "No data found for this month.\n"

        # Process year-to-date data
        if data_year:
            response_text += "\nData per Tahun:\n"
            for row in data_year:
                supplier_name = supplier_map.get(row['SUPPLIERCODEGROUP'], 'Unknown Supplier')
                netto = row['NETTO']
                total_netto_year += netto
                response_text += (f" - Kode Muatan\t\t\t: {row['JENISMUATAN']}, \n"
                                  f"   Kode Supplier\t: {row['SUPPLIERCODEGROUP']}, \n "
                                  f"   Nama Supplier\t: {supplier_name}, \n"
                                  f"   NETTO\t\t\t\t: {netto:,.0f} kg \n\n")
                index += 1
            response_text += f"**Total NETTO tahun ini: {total_netto_year:,.0f} kg**\n"
        else:
            response_text += "No data found for this year.\n"

    except Exception as e:
        response_text = f"Error fetching data: {e}"
    finally:
        if db_conn.is_connected():
            db_conn.close()

    return response_text




# Command handler to display data for a specific site and date
async def detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 2:
        await update.message.reply_text("untuk menggunakan fungsi ini ketikan dengan format sebagai berikut.\n"
                                        "/detail <site_id> <yyyy-mm-dd>\n\n"
                                        "contoh:\n"
                                        "/detail 7F01 2024-07-13\n\n"
                                        "DAFTAR SITE_ID:\n"
                                        "1. 3P02 = PB. WAY BERULU\n"
                                        "2. 3P03 = PB. KEDATON\n"
                                        "3. 3P04 = PB. PEMATANG KIWAH\n"
                                        "4. 3P05 = PB. TULANG BUYUT\n"
                                        "5. 3P06 = PB. BETUNG\n"
                                        "6. 3P07 = PB. TALANG SANGIT\n"
                                        "7. 3P08 = PB. SUNGAI LENGI\n"
                                        "8. 3P10 = PB. MUSILANDAS\n"
                                        "9. 3P11 = PB. TEBENAN\n"
                                        "10. GP12 = PB. BATURAJA\n"
                                        "11. GP14 = PB. PADANG PELAWI\n"
                                        "12. GP15 = PB. KETAHUN\n"
                                        "13. GP16 = PB. PAGAR ALAM\n"
                                        "14. 7F01 = PB. BEKRI\n"
                                        "15. 7F06 = PB. BETUNG\n")
        return

    site_id = context.args[0]
    tanggal = context.args[1]

    # Fetch the data
    response_text = await get_data_site_tanggal(site_id, tanggal)

    # Split the message if it is too long
    messages = split_message(response_text, MAX_MESSAGE_LENGTH)
    
    # Send each part of the message separately
    for msg in messages:
        await update.message.reply_text(msg)




# Fungsi untuk mendapatkan data berat bersih tahunan
def get_yearly_net_weight(year):
    connection = get_db_connection()
    if connection:
        query = f"""
        SELECT MONTH(CRTDT) as BULAN, SUM(BERATBERSIH - GRD_RCUTKGFIX) AS NETTO_TAHUN
        FROM wbticket
        WHERE SITE_ID = '7F01'
        AND YEAR(POSTINGDT) = '{year}'
        GROUP BY BULAN;
        """
        data = pd.read_sql(query, connection)
        connection.close()
        return data
    else:
        print("Failed to connect to the database.")
        return pd.DataFrame()

# Fungsi untuk membuat diagram batang berat bersih tahunan
def plot_net_yearly_weight(data, title):
    # Menambahkan semua bulan dari Januari hingga Desember
    all_months = pd.DataFrame({'BULAN': range(1, 13)})
    data = all_months.merge(data, on='BULAN', how='left').fillna(0)
    
    if not data.empty:
        fig, ax = plt.subplots(figsize=(12, 6))
        data['BULAN'] = data['BULAN'].astype(int)
        data = data.sort_values('BULAN')
        ax.bar(data['BULAN'], data['NETTO_TAHUN'], color='skyblue')
        ax.set_title(title)
        ax.set_xlabel('Bulan')
        ax.set_ylabel('Netto (kg)')
        ax.set_xticks(data['BULAN'])
        ax.set_xticklabels([datetime(2000, m, 1).strftime('%B') for m in data['BULAN']], rotation=45, ha='right')

        # Menambahkan label data di atas batang
        for p in ax.patches:
            height = p.get_height()
            if height > 0:
                ax.annotate(f'{int(height)}', (p.get_x() + p.get_width() / 2., height),
                            ha='center', va='center', xytext=(0, 5), textcoords='offset points')

        plt.tight_layout()

        # Menyimpan diagram ke dalam buffer
        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close(fig)
        return buf
    else:
        return None

# Fungsi untuk mengontrol /yearly_net_weight di chatbot
async def send_yearly_net_weight(update: Update, context: CallbackContext) -> None:
    # Mengambil argumen tahun dari perintah
    args = context.args
    if len(args) == 1:
        try:
            # Memparsing argumen tahun
            year = int(args[0])
            # Mendapatkan data untuk tahun yang ditentukan
            data = get_yearly_net_weight(year)
            buf = plot_net_yearly_weight(data, f'Netto Tahunan per Bulan pada {year}')
            if buf:
                await update.message.reply_photo(photo=InputFile(buf))
            else:
                await update.message.reply_text("Failed to retrieve yearly net weight data.")
        except ValueError:
            await update.message.reply_text("Invalid date format. Please use YYYY format.")
    else:
        await update.message.reply_text("Please provide a year in the format YYYY. Example: /yearly_net_weight 2024")


# Fungsi untuk mendapatkan data berat bersih bulanan
def get_monthly_net_weight(year_month):
    connection = get_db_connection()
    if connection:
        query = f"""
        SELECT DAY(CRTDT) as HARI, SUM(BERATBERSIH - GRD_RCUTKGFIX) AS NETTO_BULAN
        FROM wbticket
        WHERE SITE_ID = '7F01'
        AND DATE_FORMAT(POSTINGDT, '%Y-%m') = '{year_month}'
        GROUP BY HARI;
        """
        data = pd.read_sql(query, connection)
        connection.close()
        return data
    else:
        print("Failed to connect to the database.")
        return pd.DataFrame()

# Fungsi untuk membuat diagram batang berat bersih bulanan
def plot_net_monthly_weight(data, title):
    if not data.empty:
        fig, ax = plt.subplots(figsize=(12, 6))
        data['HARI'] = data['HARI'].astype(int)
        data = data.sort_values('HARI')
        ax.bar(data['HARI'], data['NETTO_BULAN'], color='skyblue')
        ax.set_title(title)
        ax.set_xlabel('Hari')
        ax.set_ylabel('Netto (kg)')
        ax.set_xticks(data['HARI'])
        ax.set_xticklabels(data['HARI'], rotation=45, ha='right')

        # Menambahkan label data di atas batang
        for p in ax.patches:
            height = p.get_height()
            if height > 0:
                ax.annotate(f'{int(height)}', (p.get_x() + p.get_width() / 2., height),
                            ha='center', va='center', xytext=(0, 5), textcoords='offset points')

        plt.tight_layout()

        # Menyimpan diagram ke dalam buffer
        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close(fig)
        return buf
    else:
        return None  

# Fungsi untuk mengontrol /monthly_net_weight di chatbot
async def send_monthly_net_weight(update: Update, context: CallbackContext) -> None:
    # Mengambil argumen bulan dari perintah
    args = context.args
    if len(args) == 1:
        try:
            # Memparsing argumen bulan
            year_month = datetime.strptime(args[0], '%Y-%m').strftime('%Y-%m')
            # Mendapatkan data untuk bulan yang ditentukan
            data = get_monthly_net_weight(year_month)
            buf = plot_net_monthly_weight(data, f'Netto Bulanan per Hari pada {year_month}')
            if buf:
                await update.message.reply_photo(photo=InputFile(buf))
            else:
                await update.message.reply_text("Failed to retrieve monthly net weight data.")
        except ValueError:
            await update.message.reply_text("Invalid date format. Please use YYYY-MM format.")
    else:
        await update.message.reply_text("Please provide a month in the format YYYY-MM. Example: /monthly_net_weight 2024-03")


    
# Fungsi untuk mendapatkan data berat bersih harian
def get_daily_net_weight(date):
    connection = get_db_connection()
    if connection:
        query = f"""
        SELECT HOUR(CRTDT) as JAM, SUM(BERATBERSIH - GRD_RCUTKGFIX) AS NETTO_HARI
        FROM wbticket
        WHERE SITE_ID = '7F01'
        AND DATE(POSTINGDT) = '{date}'
        GROUP BY JAM;
        """
        data = pd.read_sql(query, connection)
        connection.close()
        return data
    else:
        print("Failed to connect to the database.")
        return pd.DataFrame()

# Fungsi untuk membuat diagram batang berat bersih harian
def plot_net_daily_weight(data, title):
    if not data.empty:
        fig, ax = plt.subplots(figsize=(10, 6))
        data['JAM'] = data['JAM'].astype(int)
        data = data.sort_values('JAM')
        ax.bar(data['JAM'], data['NETTO_HARI'], color='skyblue')
        ax.set_title(title)
        ax.set_xlabel('Jam')
        ax.set_ylabel('Netto (kg)')
        ax.set_xticks(range(24))
        ax.set_xticklabels([f'{i:02d}:00' for i in range(24)], rotation=45, ha='right')

        # Menambahkan label data di atas batang
        for p in ax.patches:
            height = p.get_height()
            if height > 0:
                ax.annotate(f'{int(height)}', (p.get_x() + p.get_width() / 2., height),
                            ha='center', va='center', xytext=(0, 5), textcoords='offset points')

        plt.tight_layout()

        # Menyimpan diagram ke dalam buffer
        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close(fig)
        return buf
    else:
        return None

# Fungsi untuk mengontrol /daily_net_weight di chatbot
async def send_daily_net_weight(update: Update, context: CallbackContext) -> None:
    # Mengambil argumen tanggal dari perintah
    args = context.args
    if len(args) == 1:
        try:
            # Memparsing argumen tanggal
            date = datetime.strptime(args[0], '%Y-%m-%d').date()
            # Mendapatkan data untuk tanggal yang ditentukan
            data = get_daily_net_weight(date)
            buf = plot_net_daily_weight(data, f'Netto Harian per Jam pada {date}')
            if buf:
                await update.message.reply_photo(photo=InputFile(buf))
            else:
                await update.message.reply_text("Failed to retrieve daily net weight data.")
        except ValueError:
            await update.message.reply_text("Invalid date format. Please use YYYY-MM-DD format.")
    else:
        await update.message.reply_text("Please provide a date in the format YYYY-MM-DD. Example: /daily_net_weight 2024-03-11")



# Main function to set up the Telegram bot
def main():
    # Set up the Application with your bot token
    application = ApplicationBuilder().token(TELEGRAM_API_KEY).build()

    # Register the /start command handler
    application.add_handler(CommandHandler("start", start))

    # Register the /help command handler
    application.add_handler(CommandHandler("help", help_command))
    
    # Register the /tampilkan_avg_berat_per_supplier command handler
    application.add_handler(CommandHandler("tampilkan_avg_berat_per_supplier", tampilkan_avg_berat_per_supplier))

    # Register the /info command handler
    application.add_handler(CommandHandler("info", info))

    # Register the /tampilkan_data_site_tanggal command handler
    application.add_handler(CommandHandler("detail", detail))

    application.add_handler(CommandHandler('yearly_net_weight', send_yearly_net_weight))
    application.add_handler(CommandHandler('monthly_net_weight', send_monthly_net_weight))
    application.add_handler(CommandHandler('daily_net_weight', send_daily_net_weight))

    # Register the message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Command handler untuk /tampilkan_berat_storage
    tampilkan_berat_storage_handler = CommandHandler(
        'tampilkan_berat_storage', 
        tampilkan_total_berat_per_storage
    )
    application.add_handler(tampilkan_berat_storage_handler)

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()