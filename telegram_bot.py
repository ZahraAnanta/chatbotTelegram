import os
import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import mysql.connector
from mysql.connector import Error

# Load environment variables from .env file
load_dotenv()

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
        print(f"Error connecting to MySQL database: {e}")
        return None

# Function to handle the /sites command
async def sites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db_conn = get_db_connection()
    if db_conn is None:
        await update.message.reply_text("Failed to connect to the database.")
        return

    try:
        with db_conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM sites")
            sites = cursor.fetchall()

            if sites:
                response_text = "Sites:\n"
                for site in sites:
                    response_text += f"Site Code: {site['site_kode']}\nSite Name: {site['site_name']}\nSite Region: {site['site_wilayah']}\nActive Status: {site['site_aktif']}\n\n"
            else:
                response_text = "No sites found."
    except Error as e:
        response_text = f"Error fetching sites: {e}"
    finally:
        if db_conn.is_connected():
            db_conn.close()

    await update.message.reply_text(response_text)

# Function to handle the /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Hello! Ask me anything.')

# Function to get a single site from the database by site_kode
async def get_site_data(site_kode: str) -> str:
    db_conn = get_db_connection()
    if db_conn is None:
        return "Failed to connect to the database."

    try:
        with db_conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM sites WHERE site_kode = %s", (site_kode,))
            site = cursor.fetchone()

            if site:
                response_text = f"Site details for {site['site_kode']}:\nSite Name: {site['site_name']}\nSite Region: {site['site_wilayah']}\nActive Status: {site['site_aktif']}"
            else:
                response_text = f"No site named {site_kode} found."
    except Error as e:
        response_text = f"Error fetching site: {e}"
    finally:
        if db_conn.is_connected():
            db_conn.close()

    return response_text

# Function to count offices by region
async def count_offices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db_conn = get_db_connection()
    if db_conn is None:
        await update.message.reply_text("Failed to connect to the database.")
        return

    try:
        with db_conn.cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT site_wilayah, COUNT(*) AS jumlah_kantor
                FROM sites
                GROUP BY site_wilayah
                LIMIT 100
            """)
            regions = cursor.fetchall()

            if regions:
                response_text = "Office Count by Region:\n"
                for region in regions:
                    response_text += f"Region: {region['site_wilayah']}, Offices: {region['jumlah_kantor']}\n"
            else:
                response_text = "No data found."
    except Error as e:
        response_text = f"Error fetching office count: {e}"
    finally:
        if db_conn.is_connected():
            db_conn.close()

    await update.message.reply_text(response_text)

# Function to get the status of a site
async def get_site_status(site_kode: str) -> str:
    db_conn = get_db_connection()
    if db_conn is None:
        return "Failed to connect to the database."

    try:
        with db_conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT site_kode, site_aktif FROM sites WHERE site_kode = %s", (site_kode,))
            status = cursor.fetchone()

            if status:
                response_text = (f"Kondisi Jaringan Unit {status['site_kode']} terkini:\n"
                                 f"Active Status: {'UP' if status['site_aktif'] == 1 else 'DOWN'}")
            else:
                response_text = f"No status found for site {site_kode}."
    except Error as e:
        response_text = f"Error fetching status: {e}"
    finally:
        if db_conn.is_connected():
            db_conn.close()

    return response_text

# Function to handle the /status command
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    parts = update.message.text.split()
    if len(parts) == 2:
        site_kode = parts[1]
        response_text = await get_site_status(site_kode)
    else:
        response_text = "Please provide a valid site kode. Example: /status SUNI"

    await update.message.reply_text(response_text)

# Function to handle messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = update.message.text.strip()
    response_text = ""

    # Check for specific keywords in the user's message
    if 'site' in question.lower():
        # Extract site kode from the message (assuming the format "site <site_kode>")
        parts = question.split()
        if len(parts) == 2:
            site_kode = parts[1]
            response_text = await get_site_data(site_kode)
        else:
            response_text = "Please provide a valid site kode. Example: 'site KDIR'"
    else:
        # If no specific keywords, use the generative model
        if question.strip() != '':
            response = chat.send_message(question)
            response_text = response.text
            # Save the question and response to the database
            db_conn = get_db_connection()
            if db_conn is not None:
                try:
                    with db_conn.cursor() as cursor:
                        cursor.execute("INSERT INTO chat_history (question, response) VALUES (%s, %s)", (question, response_text))
                    db_conn.commit()
                except mysql.connector.Error as e:
                    print(f"Error inserting chat history: {e}")
                finally:
                    if db_conn.is_connected():
                        db_conn.close()
        else:
            response_text = 'Please ask a question.'

    await update.message.reply_text(response_text)

# Function to get sites by region
async def get_sites_by_region(region: str) -> str:
    db_conn = get_db_connection()
    if db_conn is None:
        return "Failed to connect to the database."

    try:
        with db_conn.cursor(dictionary=True) as cursor:
            cursor.execute(f"""
                SELECT id, site_kode AS kode_kantor, site_name AS nama_kantor
                FROM sites
                WHERE site_wilayah = %s LIMIT 100
            """, (region,))
            sites = cursor.fetchall()

            if sites:
                response_text = f"Sites in {region}:\n"
                for site in sites:
                    response_text += f"ID: {site['id']}\nKode Kantor: {site['kode_kantor']}\nNama Kantor: {site['nama_kantor']}\n\n"
            else:
                response_text = f"No sites found in {region}."
    except Error as e:
        response_text = f"Error fetching sites in {region}: {e}"
    finally:
        if db_conn.is_connected():
            db_conn.close()

    return response_text

# Function to handle the /lampung command
async def lampung(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    response_text = await get_sites_by_region('1-Lampung')
    await update.message.reply_text(response_text)

# Function to handle the /palembang command
async def palembang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    response_text = await get_sites_by_region('2-Palembang')
    await update.message.reply_text(response_text)

# Function to handle the /bengkulu command
async def bengkulu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    response_text = await get_sites_by_region('3-Bengkulu')
    await update.message.reply_text(response_text)

# Function to handle the /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    response_text = (
        "Here are the commands you can use:\n\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/sites - List all sites\n"
        "/count_offices - Count offices by region\n"
        "/status <site_kode> - Get the status of a site\n"
        "/lampung - List sites in Lampung\n"
        "/palembang - List sites in Palembang\n"
        "/bengkulu - List sites in Bengkulu\n"
        "Ask a general question to get a response from the generative model."
    )
    await update.message.reply_text(response_text)

# Main function to set up the Telegram bot
def main():
    # Set up the Application with your bot token
    application = ApplicationBuilder().token(TELEGRAM_API_KEY).build()

    # Register the /start command handler
    application.add_handler(CommandHandler("start", start))

    # Register the /help command handler
    application.add_handler(CommandHandler("help", help_command))

    # Register the /sites command handler
    application.add_handler(CommandHandler("sites", sites))

    # Register the /count_offices command handler
    application.add_handler(CommandHandler("count_offices", count_offices))

    # Register the /status command handler
    application.add_handler(CommandHandler("status", status))

    # Register the /lampung command handler
    application.add_handler(CommandHandler("lampung", lampung))

    # Register the /palembang command handler
    application.add_handler(CommandHandler("palembang", palembang))

    # Register the /bengkulu command handler
    application.add_handler(CommandHandler("bengkulu", bengkulu))

    # Register the message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()

