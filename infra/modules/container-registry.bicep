param location string
param registryName string
param tags object

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' = {
  name: registryName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

output name string = registry.name
output id string = registry.id
output loginServer string = registry.properties.loginServer
