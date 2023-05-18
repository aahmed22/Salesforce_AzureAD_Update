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

