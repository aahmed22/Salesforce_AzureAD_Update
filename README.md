# Salesforce_AzureAD_Update
***Description:***
The objective of this application is to leverage Microsoft Graph API to access user account info stored in Azure Active Directory and update selected fields based on the associated users account profiles from a Salesforce Production Org.  
Thus overwriting the information present in your Azure Active Directory/O365 Tenant. 


## Setting up YML Scheduled Config File to run via Azure Pipelines (Azure Devops)
```yml
schedules:
- cron: "0 14 * * *"
  displayName: Runs Daily at 10:00am EST
  branches:
    include: 
    - main
  always: true
jobs:
- job: Linux
  pool:
    name: DevOpsPool
  steps:
  - script: |
       python3 app.py
    displayName: "Run app.py" 
```
The config file above is pretty much self explanatory. The schedule time the app.py will run is set to ***14 UTC which is 10am EST***.  
**NOTE: You must make sure to list the Azure Agent Pool name you created in your Azure DevOps**. 

Below is a link to an article I found that does a great job of showcasing how to setup a self hosted agent on a virtual machine 
to run your Azure Pipelines: https://blog.opstree.com/2022/08/30/how-to-setup-an-agent-on-azure-devops/


## Microsoft Graph API Function
```python
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

    # If needed to drop specific records
    try:
        filtered.drop(filtered[filtered['Email'] == 'user1@example.com'].index, inplace=True)
        filtered.drop(filtered[filtered['Email'] == 'user2@example.com'].index, inplace=True)
    except Exception as e:
        print(e)
        print("Operation failed")

    enabled = filtered.loc[filtered['Enabled'] == 'Yes']
    enabled['Email'] = enabled['Email'].str.lower()

    return enabled
```
**NOTE: You will need to create an Azure App Registration that has the necessary permissions to access user accounts info.**  
The main objective of this function following accessing the Microsoft Graph API is to acquire the following fields when pulling user accounts from your tenant:  
* DiplayName
* First Name
* Last Name
* Email
* Job Title
* Department 
* Manager Name
* Manager Email
* Hybrid User (Checking whether the user account is fully cloud based or not)
* Enabled (Checkign whether the user account is currently enabled or disabled blocked sign-in)

Once the loop finishes we return back the pandas DataFrame and **only return back user accounts that are enabled.**

## UpdateAzureActiveDirectory Function
```python
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
```
The objective of this function is to start the process of updating the selected fields in Azure Active Directory. The function splits ***merge_cloud_df*** into 10 blocks to breakdown the updating process.  
In order to update the selected fields we will have to make a **patch request** to Microsoft Graph API. Within this function I construct a log file of all operations whether they are successful or failed to update.  
The main line making the call is:
```python 
MSGraphProfileUpdate(access_token, employeeEmail, managerEmail, department, jobTitle) 
```

## MSGraphProfileUpdate Function
```python
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
```
The previous function ***UpdateAzureActiveDirectory*** makes the function call to ***MSGraphProfileUpdate*** and takes the parameter arguments and proceeds with making the update.  
Due to the fact that the update is done via an **HTTP request**, I added a **time.sleep() method** to cause a delay following the update of a user account record since this process is being done within a loop. 
