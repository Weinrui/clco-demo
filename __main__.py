
import pulumi
from pulumi_azure_native import storage
from pulumi_azure_native import resources, web
import datetime

# Create an Azure Resource Group
resource_group = resources.ResourceGroup("resource_group", location="East US")

# Create an Azure resource (Storage Account)
account = storage.StorageAccount(
    "sa",
    resource_group_name=resource_group.name,
    sku={
        "name": storage.SkuName.STANDARD_LRS,
    },
    kind=storage.Kind.STORAGE_V2,
)

# Enable static website support
static_website = storage.StorageAccountStaticWebsite(
    "staticWebsite",
    account_name=account.name,
    resource_group_name=resource_group.name,
    index_document="index.html",
)

# Create a Blob container
blob_container = storage.BlobContainer(
    "webcontainer",
    account_name=account.name,
    resource_group_name=resource_group.name,
    public_access=storage.PublicAccess.NONE,  # Make it private since it's for app reference
)

# Create an AssetArchive for the local folder and upload as ZIP
archive_blob = storage.Blob(
    "website.zip",
    resource_group_name=resource_group.name,
    account_name=account.name,
    container_name=blob_container.name,
    source=pulumi.AssetArchive({
         "clco-demo/": pulumi.FileArchive("clco-demo/"),
    }),
    content_type="application/zip",
)

# Generate SAS Token for the Blob
def get_sas_token(args):
    account_name, container_name, blob_name = args
    sas_token = storage.list_storage_account_service_sas(
        account_name=account_name,
        protocols=storage.HttpProtocol.HTTPS,
        shared_access_start_time=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        shared_access_expiry_time=(datetime.datetime.utcnow() + datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        resource=storage.SignedResource.C,
        permissions=storage.Permissions.R,
        resource_group_name=resource_group.name,
        canonicalized_resource=f"/blob/{account_name}/{container_name}",
        content_disposition="",
        content_encoding="",
        content_language="",
        content_type="",
        cache_control=""
    )
    return sas_token.service_sas_token

sas_token = pulumi.Output.all(account.name, blob_container.name, archive_blob.name).apply(get_sas_token)

# Construct the SAS URL
blob_url_with_sas = pulumi.Output.all(account.name, blob_container.name, archive_blob.name, sas_token).apply(
    lambda args: f"https://{args[0]}.blob.core.windows.net/{args[1]}/{args[2]}?{args[3]}"
)

# Create an App Service Plan for the Web App
app_service_plan = web.AppServicePlan(
    "appServicePlan",
    resource_group_name=resource_group.name,
    sku=web.SkuDescriptionArgs(
        name="B1",  # Basic Tier
        tier="Basic",
        size="B1",
        capacity=1,
    ),
)

# Create a Web App and reference the ZIP Blob in SiteConfigArgs
web_app = web.WebApp(
    "webApp",
    resource_group_name=resource_group.name,
    server_farm_id=app_service_plan.id,
    site_config=web.SiteConfigArgs(
        app_settings=[
            web.NameValuePairArgs(name="WEBSITE_RUN_FROM_PACKAGE", value=blob_url_with_sas),
        ],
        default_documents=["clco-demo/templates/index.html"],
    ),
)

# Export the primary key of the Storage Account
primary_key = (
    pulumi.Output.all(resource_group.name, account.name)
    .apply(
        lambda args: storage.list_storage_account_keys(
            resource_group_name=args[0], account_name=args[1]
        )
    )
    .apply(lambda accountKeys: accountKeys.keys[0].value)
)

# Export URLs
pulumi.export("primary_storage_key", primary_key)
pulumi.export("blob_url", blob_url_with_sas)
pulumi.export("app_url", web_app.default_host_name)


