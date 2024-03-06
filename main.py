import email as email_lib
from pymongo import MongoClient
import imaplib
from email import policy
from email.parser import BytesParser
from bs4 import BeautifulSoup
import re
from datetime import datetime

def fetch_last_email_content(email_address, password):
    """
    Connects to a Gmail account and fetches the content of the last email in the inbox.

    :param email_address: Your Gmail email address.
    :param password: Your Gmail password or app-specific password.
    :return: Raw email content of the last email.
    """
    try:
        # Connect to Gmail's IMAP server
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(email_address, password)
        mail.select('inbox')

        # Search for all emails in the inbox
        status, email_ids = mail.search(None, 'ALL')
        if status != 'OK':
            print("No emails found!")
            return None

        # Fetch the last email ID
        last_email_id = email_ids[0].split()[-1]
        status, email_data = mail.fetch(last_email_id, '(RFC822)')
        if status != 'OK':
            print("Failed to fetch the email.")
            return None

        raw_email = email_data[0][1]

        # Close the connection and logout
        mail.close()
        mail.logout()

        return raw_email, last_email_id.decode()
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


# Example usage
# email_content = fetch_last_email_content('your_email@gmail.com', 'your_password')

def parse_email_content(email_content):
    msg = BytesParser(policy=policy.default).parsebytes(email_content)

    # Initial structure for extracted data
    extracted_data = {
        'route_name': None,
        'route': None,
        'pick_up_date': None,
        'pick_up_time': None,
        'total_cases': None,
        'items': [],
        'additional_items_needed': None,
    }

    # Helper function to parse HTML and extract table data, skipping the header row
    def extract_table_from_html(html_body):
        soup = BeautifulSoup(html_body, 'html.parser')
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')
            for row in rows[1:]:  # Skip the first row (header) using [1:]
                cols = row.find_all('td')
                if cols:
                    extracted_data['items'].append([col.text.strip() for col in cols])

    # Function to extract additional order details from the email content
    def extract_order_details(html_body):
        soup = BeautifulSoup(html_body, 'html.parser')

        # Patterns for each piece of order detail, adjust as necessary
        details_patterns = {
            'route_name': "Route Name",
            'route': "Route Number",
            'pick_up_date': "Pick up Date",
            'pick_up_time': "Pick up Time",
            'total_cases': "Total Cases",
            'additional_items_needed': "Additional Items Needed",
        }

        for key, label in details_patterns.items():
            pattern = re.compile(f"{label}:?\\s*(.*)", re.IGNORECASE)
            result = soup.find(string=pattern)
            if result:
                match = pattern.search(result)
                if match:
                    extracted_data[key] = match.group(1).strip()

    # Determine whether the email content is multipart and extract accordingly
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/html":
                html_content = part.get_content()
                extract_table_from_html(html_content)
                extract_order_details(html_content)  # Extract additional details
                break
    else:
        if msg.get_content_type() == "text/html":
            html_content = msg.get_content()
            extract_table_from_html(html_content)
            extract_order_details(html_content)  # Extract additional details

    return extracted_data

# Example usage
# raw_email_content = fetch_last_email_content('your_email@gmail.com', 'your_password')
# parsed_data = parse_email(raw_email_content)


def insert_order_into_mongodb(extracted_data, client, db_name='mydatabase', orders_collection='orders'):
    """
    Inserts the order details into a MongoDB collection.

    :param extracted_data: The data to be inserted, including the order details.
    :param client: MongoDB client instance.
    :param db_name: The name of the database.
    :param orders_collection: The name of the collection for orders.
    """
    # Check if the necessary data is available
    if not extracted_data['items']:
        print("Missing items in order details.")
        return

    # Prepare the document to be inserted
    try:
        pick_up_date = datetime.strptime(extracted_data['pick_up_date'], "%Y-%m-%d") if extracted_data.get('pick_up_date') else None
    except ValueError as e:
        print(f"Error parsing pick_up_date: {e}")
        pick_up_date = None

    order_document = {
        'route_name': extracted_data.get('route_name'),
        'route': extracted_data.get('route'),
        'pick_up_date': pick_up_date,
        'pick_up_time': extracted_data.get('pick_up_time'),
        'total_cases': extracted_data.get('total_cases'),
        'items': extracted_data['items'],  # Assuming items is a list of dictionaries
        'status': "Received",
    }

    # Select the database and collection
    db = client[db_name]
    orders_col = db[orders_collection]

    # Insert the document into the orders collection
    result = orders_col.insert_one(order_document)
    print(f"Order data inserted with record id: {result.inserted_id}")

    # Generate transfer_ID (e.g., using the last 4 characters of the MongoDB _id)
    transfer_id = str(result.inserted_id)[-4:]

    # Update the document with the transfer_ID
    orders_col.update_one({'_id': result.inserted_id}, {'$set': {'transfer_id': transfer_id}})

    print(f"Order updated with transfer_id: {transfer_id}")



# Example usage
# parsed_data = parse_email(raw_email_content)
# insert_order_into_mongodb(parsed_data)
def get_last_parsed_email_id(client, db_name='mydatabase', status_collection='status'):
    db = client[db_name]
    collection = db[status_collection]
    status_document = collection.find_one({'variable': 'last_parsed'})
    last_parsed_email_id = status_document.get('value') if status_document else None
    return last_parsed_email_id


def get_latest_email_id(email_address, password):
    mail = imaplib.IMAP4_SSL('imap.gmail.com')
    mail.login(email_address, password)
    mail.select('inbox')
    status, email_ids = mail.search(None, 'ALL')
    if status != 'OK':
        print("No emails found!")
        return None
    last_email_id = email_ids[0].split()[-1].decode()
    mail.close()
    mail.logout()
    return last_email_id


def fetch_unread_emails(email_address, password):
    """
    Fetches unread emails from the Gmail account.
    """
    mail = imaplib.IMAP4_SSL('imap.gmail.com')
    mail.login(email_address, password)
    mail.select('inbox')

    # Search for unread emails
    result, data = mail.search(None, 'UNSEEN')
    if result != 'OK':
        print("Failed to retrieve unread emails.")
        return []

    if data is None:
        print("All orders parsed")

    email_ids = data[0].split()
    emails = []

    for e_id in email_ids:
        result, email_data = mail.fetch(e_id, '(RFC822)')
        if result == 'OK':
            emails.append(email_data[0][1])

    mail.close()
    mail.logout()
    return emails


def check_and_parse_new_emails(email_address, email_password, client, db_name='mydatabase', orders_collection='orders'):
    """
    Fetches unread emails, parses them, and inserts order details into MongoDB.
    """
    unread_emails = fetch_unread_emails(email_address, email_password)

    for raw_email in unread_emails:
        email_message = email_lib.message_from_bytes(raw_email)
        subject = str(email_lib.header.make_header(email_lib.header.decode_header(email_message['Subject'])))

        if 'Concord Peet\'s Route Replenishment Submission' in subject:
            parsed_data = parse_email_content(raw_email)
            if parsed_data is not None:
                insert_order_into_mongodb(parsed_data, client, db_name, orders_collection)


# Example usage
# client = MongoClient('mongodb://localhost:27017/')  # or your MongoDB connection details
# check_and_parse_new_emails('your_email@gmail.com', 'your_password', client)


if __name__ == '__main__':
    email = "GJTat901@gmail.com"
    password = "xnva kbzm flsa szzo"
    uri = "mongodb+srv://gjtat901:koxbi2-kijbas-qoQzad@cluster0.abxr6po.mongodb.net/?retryWrites=true&w=majority"
    client = MongoClient(uri)

    check_and_parse_new_emails(email, password, client, 'mydatabase', 'orders')
