targetScope = 'subscription'

@minLength(1)
@maxLength(64)
param environmentName string

@minLength(1)
param location string

param sessionId string
param deployedBy string
param createdAt string
param resourceGroupName string
param containerAppEnvironmentName string
param containerAppName string
param registryName string
param workspaceName string
param deployerObjectId string
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@secure()
param visionKey string = ''

param visionEndpoint string = ''

var tags = {
  'app-onboard-skill': 'true'
  'app-onboard-session-id': sessionId
  'created-at': createdAt
  environment: environmentName
  'deployed-by': deployedBy
}

resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module registry './modules/container-registry.bicep' = {
  name: 'containerRegistry'
  scope: rg
  params: {
    location: location
    registryName: registryName
    tags: tags
  }
}

module platform './modules/container-app-platform.bicep' = {
  name: 'containerAppPlatform'
  scope: rg
  params: {
    location: location
    containerAppEnvironmentName: containerAppEnvironmentName
    workspaceName: workspaceName
    tags: tags
  }
}

module app './modules/container-app.bicep' = {
  name: 'containerApp'
  scope: rg
  params: {
    location: location
    containerAppName: containerAppName
    containerAppEnvironmentId: platform.outputs.environmentId
    registryName: registry.outputs.name
    registryLoginServer: registry.outputs.loginServer
    deployerObjectId: deployerObjectId
    containerImage: containerImage
    visionEndpoint: visionEndpoint
    visionKey: visionKey
    tags: tags
  }
}

output resourceGroupName string = rg.name
output registryName string = registry.outputs.name
output registryLoginServer string = registry.outputs.loginServer
output containerAppName string = app.outputs.name
output containerAppFqdn string = app.outputs.fqdn
