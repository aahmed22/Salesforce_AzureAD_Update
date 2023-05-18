import requests, msal, json, os, time, numpy
import pandas as pd
from simple_salesforce import Salesforce
from pathlib import Path
import email, smtplib, ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import client_id, tenant_id, client_secret, sf_username, sf_passwd, sf_token, smtp_host, smtp_user, smtp_passwd, port


def GraphAPICall():
    app = msal.ConfidentialClientApplication(
    client_id=client_id,
    client_credential=client_secret,
    authority='https://login.microsoftonline.com/' + tenant_id
    ) # Acquire an access token for the Microsoft Graph API
    result = app.acquire_token_for_client(scopes=['https://graph.microsoft.com/.default'])
    access_token = result['access_token']

    # Set the API endpoint and query parameters
    api_endpoint = "https://graph.microsoft.com/v1.0/users"
    query_params = {
        "$select": "displayName,givenName,surname,userPrincipalName,jobTitle,department,manager,onPremisesSyncEnabled,accountEnabled",
        "$expand": "manager($select=displayName,userPrincipalName)"
    }

    # Set the authorization header with the access token obtained from Azure AD
    #access_token = "<your_access_token_here>"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # Send the initial GET request to the API endpoint with the query parameters and authorization header
    response = requests.get(api_endpoint, params=query_params, headers=headers)

    # Parse the JSON response and get the initial set of results
    response_data = response.json()
    users = response_data["value"]
    next_link = response_data.get("@odata.nextLink")

    # Loop through the remaining pages of results and concatenate with the initial set
    while next_link:
        response = requests.get(next_link, headers=headers)
        response_data = response.json()
        users += response_data["value"]
        next_link = response_data.get("@odata.nextLink")

    # Create a pandas DataFrame from the retrieved user data
    user_data = []
    for user in users:
        user_data.append({
            "Name": user['displayName'],
            "First Name": user['givenName'],
            "Last Name": user['surname'],
            "Email": user['userPrincipalName'],
            "Job Title": user['jobTitle'],
            "Department": user['department'],
            "Manager Name": user.get("manager", {}).get("displayName", ""),
            "Manager Email": user.get("manager", {}).get("userPrincipalName", ""),
            "Hybrid User": "Yes" if user["onPremisesSyncEnabled"] else "No",
            "Enabled": "Yes" if user["accountEnabled"] else "No"
        })

    ndf = pd.DataFrame(user_data)
    filtered = ndf[ndf['Email'].str.contains("@example.com")]
    filtered = filtered[(filtered['First Name'].notnull()) & (filtered['Last Name'].notnull() & (filtered['Job Title'].notnull()))]
    filtered = filtered[(filtered['Manager Name'].notnull())]

    # Drop specific records
    # This 
    try:
        filtered.drop(filtered[filtered['Email'] == 'user1@example.com'].index, inplace=True)
        filtered.drop(filtered[filtered['Email'] == 'user2@example.com'].index, inplace=True)
    except Exception as e:
        print(e)
        print("Operation failed")

    enabled = filtered.loc[filtered['Enabled'] == 'Yes']
    enabled['Email'] = enabled['Email'].str.lower()

    return enabled


def SFEmployeeProfiles():
    # Pull Employee Profiles from Salesforce
    new_sf = Salesforce(username=sf_username, password=sf_passwd, security_token=sf_token)
    # Enter your selected fields to query from your Salesforce Org
    field_list = ['Id', 'Employee_Email', 'Name', 'Title', 'Start_Date', 'Team', 'Managers']
    custom_sf_object = "ENTER CUSTOM SALESFORCE OBJECT NAME"

    employee_results = new_sf.query_all("SELECT " + ','.join(field_list) + " FROM " + custom_sf_object + " WHERE Employee_Status = 'Active' AND EmployeeId != ''")
    employee_data = pd.DataFrame.from_dict(employee_results['records'], orient='columns')
    del employee_data['attributes']

    # Gather Manager's IDs and Merge Names
    manager_ids = employee_data[['Id', 'Name', 'Employee_Email']]
    manager_ids = manager_ids.rename(columns={"Id":"MGRID", "Name":"ManagerName", "Employee_Email":"ManagerEmail"})
    #Merge Employee Profiles and Manager Info
    sf_profiles = pd.merge(employee_data, manager_ids, left_on=["Managers"], right_on=["MGRID"], how="left").drop(['Managers', 'MGRID'], axis=1) 

    try:
        sf_profiles.drop(sf_profiles[sf_profiles['Employee_Email'] == 'user1@example.com'].index, inplace=True)
        sf_profiles.drop(sf_profiles[sf_profiles['Employee_Email'] == 'user2@example.com'].index, inplace=True)
    except Exception as e:
        print(e)
        print("Operation Failed!")
    
    sf_profiles = sf_profiles.rename(columns={"Name":"EmployeeName"})
    return sf_profiles


def CloudOperations(cloud, salesforce_df):
    merge_cloud = pd.merge(cloud, salesforce_df, left_on=["Email"], right_on=["Employee_Email"], how="outer", indicator=True)
    merge_cloud = merge_cloud.drop(['First Name', 'Last Name'], axis=1)
    cloud_users = merge_cloud.loc[merge_cloud['_merge'] == 'both']
    try:
        cloud_users["ManagerEmail"] = cloud_users["ManagerEmail"].replace(to_replace='usr1@example.com', value='user1@example.com', regex=True)
        cloud_users["ManagerEmail"] = cloud_users["ManagerEmail"].replace(to_replace='usr2@example.com', value='user2@example.com', regex=True)
    except Exception as e:
        print(e)
        print("Operation Failed!")

    return cloud_users


def AcquireGraphToken():
    app = msal.ConfidentialClientApplication(
    client_id=client_id,
    client_credential=client_secret,
    authority='https://login.microsoftonline.com/' + tenant_id
    ) # Acquire an access token for the Microsoft Graph API
    result = app.acquire_token_for_client(scopes=['https://graph.microsoft.com/.default'])
    access_token = result['access_token']
    return access_token


def UpdateAzureActiveDirectory(access_token, merge_cloud_df):
    cloud_split = numpy.array_split(merge_cloud_df, 10)
    index = 0
    log_dict = {
        "Name": [], 
        "Email": [], 
        "Title": [],
        "Department": [],
        "Manager": [],
        "ManagerEmail": [],
        "Status": []
    }

    for index in range(len(cloud_split)):
        for key, value in cloud_split[index].iterrows():
            department = value['Team']
            employeeName = value['Name']
            employeeEmail = value['Employee_Email']
            jobTitle = value['Title']
            managerName = value['ManagerName']
            managerEmail = value['ManagerEmail']
        
            print(f"Team: {department}")
            print(f"Employee: {employeeName}, Email: {employeeEmail}, JobTitle: {jobTitle}, Manager Email: {managerEmail}")
            
            try:
                logStatus = "SUCCESS!"
                print("Calling Graph Execution!")
                MSGraphProfileUpdate(access_token, employeeEmail, managerEmail, department, jobTitle)
                print("OPERATION SUCCESSFUL!!!\n")
                log_dict["Name"].append(value['EmployeeName'])
                log_dict["Email"].append(value['Email'])
                log_dict["Title"].append(value['Title'])
                log_dict["Department"].append(value['Team'])
                log_dict["Manager"].append(value['ManagerName'])
                log_dict["ManagerEmail"].append(value['ManagerEmail'])
                log_dict["Status"].append(logStatus)
                time.sleep(5)
            except Exception as e:
                print(e)
                print("Operation Failed!")
                print(f"Employee: {employeeName}, Email: {employeeEmail}, JobTitle: {jobTitle}, Manager: {managerName}, Manager Email: {managerEmail}")
                print("\n\n")
                logStatus = "FAILIED!"
                log_dict["Name"].append(value['EmployeeName'])
                log_dict["Email"].append(value['Email'])
                log_dict["Title"].append(value['Title'])
                log_dict["Department"].append(value['Team'])
                log_dict["Manager"].append(value['ManagerName'])
                log_dict["ManagerEmail"].append(value['ManagerEmail'])
                log_dict["Status"].append(logStatus)

        print(f"Round {index} Completed...\n")
        print()

    custom_df = pd.DataFrame.from_dict(log_dict)
    print("custom")
    print(custom_df)
    custom_file = "AzureADProfileLogs.xlsx"
    custom_df.to_excel(custom_file, index=False, header=True)
    sendEmail("Azure AD Profile Updates are now complete!", "Employee Profiles for fields Title, Department and Manager have been updated!", custom_file)
    deleteLogFile(Path(custom_file))

def MSGraphProfileUpdate(access_token, user_upn, new_manager_upn, new_department, job_title):
   
    url = f"https://graph.microsoft.com/v1.0/users/{user_upn}"
 
    headers = {
        "Authorization": "Bearer " + access_token
    }
    
    response = requests.get(url, headers=headers)
    user = response.json()
    response = requests.get(f"https://graph.microsoft.com/v1.0/users/{new_manager_upn}", headers=headers)
    new_manager = response.json()

    # Define the request body
    data = {
        "manager@odata.bind": f"https://graph.microsoft.com/v1.0/users/{new_manager['id']}",
        "department": new_department,
        "jobTitle": job_title,
    }

    # Define the headers
    headers = {
        "Authorization": "Bearer " + access_token,
        "Content-Type": "application/json"
    }


    #print("Output:", data)
    #print()
    # Send the PATCH request to update the user's Manager and Department properties
    response = requests.patch(url, headers=headers, data=json.dumps(data))

    # Check the response status code
    if response.status_code == 204:
        print(f"Manager and Department properties updated successfully for user {user_upn}.")
    else:
        print(response.text)
        print(f"Error updating Manager and Department properties for user {user_upn}: " + response.text)
    
    print("Standby For next execution Run...\n")
    time.sleep(3)


def sendEmail(custom_subject, custom_body, custom_file):
    
    try:
        notification_list = 'admin1@example.com, admin2@example.com'
        smtp_server = smtplib.SMTP(smtp_host, port)
        message = MIMEMultipart()
        message['Subject'] = custom_subject
        message['From'] = smtp_user
        message['To'] = notification_list
        body = custom_body
        message.attach(MIMEText(body, "plain"))

        filename = custom_file
        attachment = open(Path(filename), "rb")

        part = MIMEBase('application', 'octet-stream')
        part.set_payload((attachment).read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', "attachment; filename = %s" % filename)
        message.attach(part)

        smtp_server.ehlo()
        smtp_server.starttls()
        smtp_server.ehlo()
        smtp_server.login(smtp_user, smtp_passwd)
        text = message.as_string()

        smtp_server.sendmail(smtp_user, notification_list, text)
        smtp_server.quit()
    except Exception as e:
        print(e)
        print("Attempt to send email notification failed!\n")
    finally:
        smtp_server.close()


def deleteLogFile(path):
    print("Deleting file...")
    os.remove(path)


if __name__ == "__main__":
    aad_accounts = GraphAPICall()
    cloud = aad_accounts.loc[aad_accounts['Hybrid User'] == 'No']
   
    salesforce_df = SFEmployeeProfiles()
    merge_cloud_df = CloudOperations(cloud, salesforce_df)
    access_token = AcquireGraphToken()
    UpdateAzureActiveDirectory(access_token, merge_cloud_df)    