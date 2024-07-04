import os
import google.generativeai as genai
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackContext,filters, ContextTypes
import mysql.connector
from mysql.connector import Connect, Error
import pandas as pd
import sys

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
            cursor.execute("SELECT * FROM sites WHERE site_wilayah = %s", (region,))
            sites = cursor.fetchall()

            if sites:
                response_text = f"Sites in {region}:\n"
                for site in sites:
                    response_text += f"Site Code: {site['site_kode']}\nSite Name: {site['site_name']}\n\n"
            else:
                response_text = f"No sites found in {region}."
    except Error as e:
        response_text = f"Error fetching sites: {e}"
    finally:
        if db_conn.is_connected():
            db_conn.close()

    return response_text

# Function to handle the /lampung command
async def lampung(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    response_text = await get_sites_by_region('LAMPUNG')
    await update.message.reply_text(response_text)

# Function to handle the /palembang command
async def palembang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    response_text = await get_sites_by_region('PALEMBANG')
    await update.message.reply_text(response_text)

# Function to handle the /bengkulu command
async def bengkulu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    response_text = await get_sites_by_region('BENGKULU')
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
        "/check_unupdated_tickets - Check for unupdated tickets\n"
        "Ask a general question to get a response from the generative model."
    )
    await update.message.reply_text(response_text)

# Function to check for unupdated tickets
def check_unupdated_tickets():
    db_conn = get_db_connection()
    if db_conn is None:
        return "Failed to connect to the database."

    try:
        query = """
        SELECT NOTICKET, COMP_ID, CRTBY, CRTDT, UPDDT
        FROM wbticket
        """
        data = pd.read_sql(query, db_conn)

        # Convert date columns to datetime
        data['CRTDT'] = pd.to_datetime(data['CRTDT'], errors='coerce')
        data['UPDDT'] = pd.to_datetime(data['UPDDT'], errors='coerce')

        # Identify tickets that have not been updated
        unupdated_tickets = data[data['UPDDT'].isna()]

        # Display ticket number, comp_id, and crtby for unupdated tickets
        if not unupdated_tickets.empty:
            result = unupdated_tickets[['NOTICKET', 'COMP_ID', 'CRTBY']]
            return result.to_json(orient="records")
        else:
            return "Semua tiket sudah diupdate."
    except Error as e:
        return f"Error fetching data: {e}"
    finally:
        if db_conn.is_connected():
            db_conn.close()

# Function to handle the /analyze_tickets command with date input
async def analyze_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Please enter a date (YYYY-MM-DD) for ticket analysis:")

# Function to handle message input for ticket analysis
async def handle_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    input_date = update.message.text.strip()

    # Load data from the database
    db_conn = get_db_connection()
    if db_conn is None:
        await update.message.reply_text("Failed to connect to the database.")
        return

    try:
        with db_conn.cursor(dictionary=True) as cursor:
            # Fetch ticket data from the database
            cursor.execute("""
                SELECT CRTDT, UPDDT, COMP_ID, STORAGE, NOTICKET
                FROM wbticket 
                WHERE POSTINGDT IS NOT NULL AND UPDDT IS NOT NULL
            """)
            rows = cursor.fetchall()

            if rows:
                # Create a DataFrame from the rows
                data = pd.DataFrame(rows)

                # Convert CRTDT and UPDDT columns to datetime
                data['CRTDT'] = pd.to_datetime(data['CRTDT'], errors='coerce')
                data['UPDDT'] = pd.to_datetime(data['UPDDT'], errors='coerce')

                # Drop rows with invalid dates
                data = data.dropna(subset=['CRTDT', 'UPDDT'])

                # Filter data based on input date
                filtered_data = data[data['CRTDT'].dt.date == pd.to_datetime(input_date).date()]

                if not filtered_data.empty:
                    # Calculate processing time in hours
                    filtered_data['Processing_Time_Hours'] = (filtered_data['UPDDT'] - filtered_data['CRTDT']).dt.total_seconds() / 3600

                    # Calculate average processing time per company
                    company_processing_time = filtered_data.groupby('COMP_ID')['Processing_Time_Hours'].mean()

                    # Print average processing time per company
                    response_text = f"\nAverage Processing Time per Company on {input_date}:\n\n"
                    for comp_id, avg_time in company_processing_time.items():
                        response_text += f"Company: {comp_id}, Average Processing Time: {avg_time:.2f} hours\n"

                    # Send response
                    await update.message.reply_text(response_text)

                    # Show details for each company
                    for comp_id, group in filtered_data.groupby('COMP_ID'):
                        response_text = f"\nCompany: {comp_id}\n"
                        for index, row in group[['CRTDT', 'STORAGE', 'NOTICKET']].iterrows():
                            response_text += f"Date: {row['CRTDT']}, Storage: {row['STORAGE']}, Ticket Number: {row['NOTICKET']}\n"
                        await update.message.reply_text(response_text)

                    # Plot distribution of processing time per company
                    plt.figure(figsize=(10, 6))
                    for comp_id, group in filtered_data.groupby('COMP_ID'):
                        plt.hist(group['Processing_Time_Hours'].dropna(), bins=20, alpha=0.6, label=comp_id, edgecolor='black')

                    plt.title(f'Distribution of Processing Time per Company on {input_date}')
                    plt.xlabel('Processing Time (hours)')
                    plt.ylabel('Frequency')
                    plt.legend()
                    plt.grid(True)
                    plt.tight_layout()

                    # Save plot to file
                    plot_filename = 'ticket_processing_time.png'
                    plt.savefig(plot_filename)

                    # Send plot as photo
                    await context.bot.send_photo(chat_id=update.message.chat_id, photo=open(plot_filename, 'rb'))

                    # Clear plot for next use
                    plt.clf()
                else:
                    await update.message.reply_text(f"No ticket data found for {input_date}.")
            else:
                await update.message.reply_text("No ticket data found in the database.")
    except Error as e:
        await update.message.reply_text(f"Error analyzing tickets: {e}")
    finally:
        if db_conn.is_connected():
            db_conn.close()


# Function to handle the /check_unupdated_tickets command
async def check_unupdated_tickets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    result = check_unupdated_tickets()
    await update.message.reply_text(result)

# Function to analyze tickets from the database based on input date
def analyze_tickets_from_db(host, user, password, database, input_date):
    try:
        # Establish MySQL connection
        connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database
        )

        if connection.is_connected():
            # Query to fetch ticket data for the input date
            query = f"""
            SELECT NOTICKET, COMP_ID, CRTBY, CRTDT, UPDDT, STORAGE
            FROM wbticket
            WHERE DATE(CRTDT) = '{input_date}'
            """
            data = pd.read_sql(query, connection)

            # Convert date columns to datetime
            data['CRTDT'] = pd.to_datetime(data['CRTDT'], errors='coerce')
            data['UPDDT'] = pd.to_datetime(data['UPDDT'], errors='coerce')

            # Drop rows with invalid dates
            data = data.dropna(subset=['CRTDT', 'UPDDT'])

            # Calculate processing time in hours
            data['Processing_Time_Hours'] = (data['UPDDT'] - data['CRTDT']).dt.total_seconds() / 3600

            # Group by company and calculate mean processing time
            company_processing_time = data.groupby('COMP_ID')['Processing_Time_Hours'].mean()

            # Plot distribution of processing time per company
            plt.figure(figsize=(10, 6))
            for COMP_ID, group in data.groupby('COMP_ID'):
                plt.hist(group['Processing_Time_Hours'].dropna(), bins=20, alpha=0.6, label=COMP_ID, edgecolor='black')

            plt.title(f'Distribution of Processing Time per Company on {input_date}')
            plt.xlabel('Processing Time (hours)')
            plt.ylabel('Frequency')
            plt.legend()
            plt.grid(True)
            histogram_filename = f'ticket_processing_time_{input_date}.png'
            plt.savefig(histogram_filename)  # Save histogram as an image file
            plt.close()

            # Summary statistics of processing time
            processing_time_summary = company_processing_time.describe()

            # Conclusion based on average processing time
            average_processing_time = processing_time_summary['mean']
            threshold_hours = 24  # Threshold for reasonable processing time

            if average_processing_time < threshold_hours:
                conclusion = f"The system is effective because the average processing time is {average_processing_time:.2f} hours, which is faster than the threshold ({threshold_hours} hours)."
            else:
                conclusion = f"The system is less effective because the average processing time is {average_processing_time:.2f} hours, which is slower than the threshold ({threshold_hours} hours)."

            return processing_time_summary, conclusion, histogram_filename

    except mysql.connector.Error as e:
        print(f"Error while connecting to MySQL: {e}")
        return None, None, None

    finally:
        if 'connection' in locals() and connection.is_connected():
            connection.close()







def analyze_tickets_data(data, input_date):
    data['CRTDT'] = pd.to_datetime(data['CRTDT'], errors='coerce')
    data['UPDDT'] = pd.to_datetime(data['UPDDT'], errors='coerce')
    data = data.dropna(subset=['CRTDT', 'UPDDT'])
    data['Processing_Time_Hours'] = (data['UPDDT'] - data['CRTDT']).dt.total_seconds() / 3600
    filtered_data = data[data['CRTDT'].dt.date == pd.to_datetime(input_date).date()]

    if not filtered_data.empty:
        company_processing_time = filtered_data.groupby('COMP_ID')['Processing_Time_Hours'].mean()
        response_text = f"\nAverage Processing Time per Company on {input_date}:\n\n"
        for comp_id, avg_time in company_processing_time.items():
            response_text += f"Company: {comp_id}, Average Processing Time: {avg_time:.2f} hours\n"
        for comp_id, group in filtered_data.groupby('COMP_ID'):
            response_text += f"\nCompany: {comp_id}\n"
            for index, row in group[['CRTDT', 'STORAGE', 'NOTICKET']].iterrows():
                response_text += f"Date: {row['CRTDT']}, Storage: {row['STORAGE']}, Ticket Number: {row['NOTICKET']}\n"
        plt.figure(figsize=(10, 6))
        for comp_id, group in filtered_data.groupby('COMP_ID'):
            plt.hist(group['Processing_Time_Hours'].dropna(), bins=20, alpha=0.6, label=comp_id, edgecolor='black')
        plt.title(f'Distribution of Processing Time per Company on {input_date}')
        plt.xlabel('Processing Time (hours)')
        plt.ylabel('Frequency')
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plot_filename = 'ticket_processing_time.png'
        plt.savefig(plot_filename)
        plt.clf()
        return response_text, plot_filename
    else:
        return f"No ticket data found for {input_date}.", None

async def analyze_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("Please provide a date in the format YYYY-MM-DD.")
        return
    input_date = args[0]
    try:
        pd.to_datetime(input_date).date()
    except ValueError:
        await update.message.reply_text("Invalid date format. Please use YYYY-MM-DD.")
        return
    db_conn = get_db_connection()
    if db_conn is None:
        await update.message.reply_text("Failed to connect to the database.")
        return
    try:
        with db_conn.cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT CRTDT, UPDDT, COMP_ID, STORAGE, NOTICKET
                FROM wbticket 
                WHERE POSTINGDT IS NOT NULL AND UPDDT IS NOT NULL
            """)
            rows = cursor.fetchall()
            if rows:
                data = pd.DataFrame(rows)
                response_text, plot_filename = analyze_tickets_data(data, input_date)
                max_message_length = 4096
                for i in range(0, len(response_text), max_message_length):
                    await update.message.reply_text(response_text[i:i + max_message_length])
                if plot_filename:
                    await context.bot.send_photo(chat_id=update.message.chat_id, photo=open(plot_filename, 'rb'))
            else:
                await update.message.reply_text("No ticket data found in the database.")
    except Error as e:
        await update.message.reply_text(f"Error analyzing tickets: {e}")
    finally:
        if db_conn.is_connected():
            db_conn.close()


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

    # Register the /check_unupdated_tickets command handler
    application.add_handler(CommandHandler("check_unupdated_tickets", check_unupdated_tickets_command))

    application.add_handler(CommandHandler("analyze_tickets", analyze_tickets))

    # Register the message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()
