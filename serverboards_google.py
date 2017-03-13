#!env/bin/python

import serverboards, requests
from serverboards import rpc
from urllib.parse import urlencode, urljoin
from oauth2client import client
import httplib2, threading
import datetime
from googleapiclient import discovery

OAUTH_AUTH_URL="https://accounts.google.com/o/oauth2/auth"
OAUTH_AUTH_TOKEN_URL="https://accounts.google.com/o/oauth2/token"
OAUTH_AUTH_REVOKE_URL="https://accounts.google.com/o/oauth2/token"
SCOPES = []
settings = {}
PLUGIN_ID=None

def setup(plugin_id=None, **kwargs):
    if plugin_id:
        global PLUGIN_ID
        PLUGIN_ID=plugin_id
    if kwargs.get("settings")!=None:
        global settings
        settings.update(kwargs.get("settings"))
    if kwargs.get("scopes"):
        global SCOPES
        SCOPES = kwargs.get("scopes")

def ensure_settings():
    print(settings)
    if "client_id" not in settings:
        data = serverboards.rpc.call("settings.get", PLUGIN_ID+"/settings")
        if not data:
            raise Exception("Google API Integration not configured. Check system settings.")
        settings.update(data)

        base = serverboards.rpc.call("settings.get", "serverboards.core.settings/base")
        settings.update(base)

class ServerboardsStorage(client.Storage):
    def __init__(self, id=None):
        assert id
        self.id=id
        super(ServerboardsStorage, self).__init__(lock=threading.Lock())
    def locked_get(self):
        content = rpc.call("plugin.data.get", "credentials-"+self.id)
        if not content:
            return None
        try:
            print(content)
            credentials = client.OAuth2Credentials.from_json(content)
            credentials.set_store(self)
            return credentials
        except:
            pass
        return None

    def locked_put(self, credentials):
        rpc.call("plugin.data.update", "credentials-"+self.id, credentials.to_json())
    def locked_delete(self):
        rpc.call("plugin.data.delete", "credentials-"+self.id)

@serverboards.rpc_method
def authorize_url(service, **kwargs):
    service_id=service["uuid"]
    ensure_settings()

    params={
        "response_type" : "code",
        "client_id" : settings["client_id"],
        "redirect_uri" : urljoin(settings["base_url"], "/static/%s/auth.html"%PLUGIN_ID),
        "scope": SCOPES[0],
        "state": service_id
    }
    url = OAUTH_AUTH_URL+"?"+urlencode(params)
    return url

@serverboards.rpc_method
def store_code(service_id, code):
    ensure_settings()

    """
    Stores the code and get a refresh token and a access token
    """
    params={
        "code": code,
        "client_id": settings["client_id"],
        "client_secret": settings["client_secret"],
        "redirect_uri": urljoin(settings["base_url"], "/static/%s/auth.html"%PLUGIN_ID),
        "grant_type": "authorization_code",
    }
    response = requests.post(OAUTH_AUTH_TOKEN_URL, params)
    js = response.json()
    if 'error' in js:
        raise Exception(js['error_description'])
    storage = ServerboardsStorage(service_id)
    credentials = client.OAuth2Credentials(
        access_token=js["access_token"],
        client_id=settings["client_id"],
        client_secret=settings["client_secret"],
        refresh_token=js.get("refresh_token"),
        token_expiry=datetime.datetime.utcnow() + datetime.timedelta(seconds=int(js["expires_in"])),
        token_uri=OAUTH_AUTH_TOKEN_URL,
        user_agent=None,
        revoke_uri=OAUTH_AUTH_REVOKE_URL,
        token_response=js,
        scopes=SCOPES,
        token_info_uri="https://www.googleapis.com/oauth2/v3/tokeninfo"
    )
    credentials.set_store(storage)
    storage.put(credentials)

    return "ok"
