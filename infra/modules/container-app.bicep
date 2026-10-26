param location string
param containerAppName string
param containerAppEnvironmentId string
param registryName string
param registryLoginServer string
param deployerObjectId string
param containerImage string
param visionEndpoint string
@secure()
param visionKey string
param tags object

var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
var isPlaceholder = containerImage == placeholderImage
var targetPort = isPlaceholder ? 80 : 8501
var useVision = !isPlaceholder && !empty(visionEndpoint) && !empty(visionKey)
var plainEnvVars = [
  {
    name: 'PORT'
    value: string(targetPort)
  }
  {
    name: 'AZURE_VISION_ENDPOINT'
    value: visionEndpoint
  }
]
var visionEnvVars = useVision
  ? [
      {
        name: 'AZURE_VISION_KEY'
        secretRef: 'vision-key'
      }
    ]
  : []
var appSecrets = useVision
  ? [
      {
        name: 'vision-key'
        value: visionKey
      }
    ]
  : []

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: registryName
}

resource app 'Microsoft.App/containerApps@2026-07-01' = {
  name: containerAppName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: targetPort
        allowInsecure: false
        transport: 'auto'
      }
      registries: isPlaceholder
        ? []
        : [
            {
              server: registryLoginServer
              identity: 'system'
            }
          ]
      secrets: appSecrets
    }
    template: {
      containers: [
        {
          name: 'field-tech-copilot'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(plainEnvVars, visionEnvVars)
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: isPlaceholder ? '/' : '/_stcore/health'
                port: targetPort
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 5
              failureThreshold: 24
            }
            {
              type: 'Liveness'
              httpGet: {
                path: isPlaceholder ? '/' : '/_stcore/health'
                port: targetPort
                scheme: 'HTTP'
              }
              initialDelaySeconds: 15
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: isPlaceholder ? '/' : '/_stcore/health'
                port: targetPort
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          {
            name: 'http-scaler'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

resource appAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, app.id, '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource deployerAcrPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, deployerObjectId, '8311e382-0749-4cb8-b61a-304f252e45ec')
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '8311e382-0749-4cb8-b61a-304f252e45ec'
    )
    principalId: deployerObjectId
    principalType: 'ServicePrincipal'
  }
}

output name string = app.name
output fqdn string = app.properties.configuration.ingress.fqdn
