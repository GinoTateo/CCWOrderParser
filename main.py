
import imaplib
import email as email_lib
import re
from pymongo import MongoClient
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

def parse_email(raw_email_content, email_id):
    """
    Parses the raw content of an email, handles forwarded emails, and extracts specific data points and order details.

    :param raw_email_content: The raw email content.
    :return: A dictionary containing the extracted data points and order details.
    """
    if not raw_email_content:
        print("No email content provided.")
        return None

    email_message = email_lib.message_from_bytes(raw_email_content)

    # Define a dictionary to hold the extracted data
    extracted_data = {
        'Route Name': None,
        'Route Number': None,
        'Pick up Date': None,
        'Pick up Time': None,
        'Total Cases': None,
        'Order Details': [],
        'Email ID': email_id
    }

    def decode_payload(payload, charset='utf-8'):
        try:
            return payload.decode(charset)
        except UnicodeDecodeError:
            return payload.decode('ISO-8859-1')  # Fallback decoding

    def is_forwarded_line(line):
        patterns = [
            r"Forwarded message",
            r"Begin forwarded message",
            r"^From:",
            r"^Sent:",
            r"^To:",
            r"Original Message",
            r"^\-\- Forwarded message \-\-$"
        ]
        return any(re.search(pattern, line) for pattern in patterns)

    # Extract the body of the email
    body = ''
    if email_message.is_multipart():
        for part in email_message.walk():
            if part.get_content_type() == "text/plain":
                body = decode_payload(part.get_payload(decode=True))
                break
    else:
        body = decode_payload(email_message.get_payload(decode=True))

    # Parsing the body for the specific data points and order form
    original_email_started = False
    order_table_started = False
    item_lines = []
    found_quantity_header = False

    for line in body.splitlines():
        if is_forwarded_line(line):
            original_email_started = True
            continue
        if original_email_started:
            # Check for and extract key data points
            for key in extracted_data:
                if line.startswith(key) and not order_table_started:
                    extracted_data[key] = line.split(':', 1)[1].strip()

            # Check for the start of the order table
            if line.startswith("Item Number"):
                order_table_started = True
                continue

            # Check for the end of the order table
            if "Additional Items Needed" in line:
                break

            # Detect the 'Quantity' header to start processing items
            if order_table_started and "Quantity" in line:
                found_quantity_header = True
                continue

            # Collect lines for the order table
            if found_quantity_header and line.strip():
                item_lines.append(line.strip())

    # Process the collected item lines
    for i in range(0, len(item_lines), 3):
        try:
            extracted_data['Order Details'].append({
                'Item Number': item_lines[i],
                'Item Description': item_lines[i + 1],
                'Quantity': item_lines[i + 2]
            })
        except IndexError:
            break  # In case the list of items does not divide evenly by 3

    # Print and return the extracted data
    for key, value in extracted_data.items():
        if key != 'Order Details':
            print(f"{key}: {value}")
        else:
            print("Order Details:")
            for item in value:
                print(item)

    return extracted_data


# Example usage
# raw_email_content = fetch_last_email_content('your_email@gmail.com', 'your_password')
# parsed_data = parse_email(raw_email_content)



def insert_order_into_mongodb(extracted_data, client, db_name='mydatabase', orders_collection='orders'):
    """
    Inserts the order details into a MongoDB collection, organized by date and route.

    :param extracted_data: The data to be inserted, including the order details.
    :param db_name: The name of the database.
    :param orders_collection: The name of the collection for orders.
    """
    # Check if the necessary data is available
    if not extracted_data.get('Order Details') or not extracted_data.get('Pick up Date') or not extracted_data.get('Route Number'):
        print("Missing order details, date, or route number.")
        return

    # Select the database and collection
    db = client[db_name]
    collection = db[orders_collection]

    # Prepare the document to be inserted
    order_document = {
        'email_id': extracted_data['Email ID'],
        'date': datetime.strptime(extracted_data['Pick up Date'], "%m/%d/%Y"),  # Adjust date format if necessary
        'route': extracted_data['Route Number'],
        'orders': extracted_data['Order Details']
    }

    # Insert the document into the collection
    result = collection.insert_one(order_document)
    print(f"Order data inserted with record id: {result.inserted_id}")


# Example usage
# parsed_data = parse_email(raw_email_content)
# insert_order_into_mongodb(parsed_data)
def get_last_parsed_email_id(client, db_name='mydatabase', status_collection='status'):

    db = client[db_name]
    collection = db[status_collection]

    # Assuming there's a document with a field 'last_parsed'
    status_document = collection.find_one({'variable': 'last_parsed'})
    last_parsed_email_id = status_document.get('value') if status_document else None

    return last_parsed_email_id

def get_latest_email_id(email_address, password):
    # Connect to Gmail's IMAP server
    mail = imaplib.IMAP4_SSL('imap.gmail.com')
    mail.login(email_address, password)
    mail.select('inbox')

    # Search for all emails in the inbox
    status, email_ids = mail.search(None, 'ALL')
    if status != 'OK':
        print("No emails found!")
        return None

    # Get the last email ID
    last_email_id = email_ids[0].split()[-1].decode()

    # Close the connection and logout
    mail.close()
    mail.logout()

    return last_email_id

def check_and_parse_new_email(email_address, email_password, client, db_name='mydatabase', status_collection='status', orders_collection='orders'):
    latest_email_id = get_latest_email_id(email_address, email_password)
    last_parsed_email_id = get_last_parsed_email_id(client, db_name, status_collection)

    if latest_email_id == last_parsed_email_id:
        print("Latest email has already been parsed.")
        return
    else:
        # Fetch and parse the latest email
        raw_email_content, email_id = fetch_last_email_content(email_address, email_password)
        parsed_data = parse_email(raw_email_content, email_id)

        # Insert parsed data into MongoDB
        insert_order_into_mongodb(parsed_data, client, db_name, orders_collection)

        # Update the last parsed email ID in the status collection
        db = client[db_name]
        collection = db[status_collection]
        collection.update_one({'variable': 'last_parsed'}, {'$set': {'value': latest_email_id}}, upsert=True)
        client.close()

# Example usage
# check_and_parse_new_email('your_email@gmail.com', 'your_password')


if __name__ == '__main__':
    email = "GJTat901@gmail.com"
    password = "xnva kbzm flsa szzo"
    uri = "mongodb+srv://gjtat901:koxbi2-kijbas-qoQzad@cluster0.abxr6po.mongodb.net/?retryWrites=true&w=majority"
    client = MongoClient(uri)

    check_and_parse_new_email(email, password, client)


