targetScope = 'resourceGroup'

param location string = 'eastus2'
param accountName string
param deploymentName string = 'field-tech-explanations'

@description('Thousands of tokens per minute. This is a rate allocation, not a spending cap.')
@minValue(1)
param capacity int = 10

resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: deploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: capacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1-mini'
      version: '2025-04-14'
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

output endpoint string = account.properties.endpoint
output deploymentName string = deployment.name
