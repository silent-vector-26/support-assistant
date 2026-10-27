targetScope = 'resourceGroup'

param budgetName string

param amount int

@description('First day of a month, formatted yyyy-MM-01.')
param startDate string

@minLength(1)
param contactEmails array

@description('Percent thresholds for actual-spend alerts.')
param actualThresholds array = [
  50
  80
  100
]

@description('Percent thresholds for forecasted-spend alerts.')
param forecastThresholds array = [
  100
]

var actualNotifications = [for threshold in actualThresholds: {
  key: 'actual-${threshold}'
  value: {
    enabled: true
    operator: 'GreaterThanOrEqualTo'
    threshold: threshold
    thresholdType: 'Actual'
    contactEmails: contactEmails
  }
}]

var forecastNotifications = [for threshold in forecastThresholds: {
  key: 'forecast-${threshold}'
  value: {
    enabled: true
    operator: 'GreaterThanOrEqualTo'
    threshold: threshold
    thresholdType: 'Forecasted'
    contactEmails: contactEmails
  }
}]

// Budgets only notify; they do not stop or throttle resources.
resource budget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: budgetName
  properties: {
    category: 'Cost'
    amount: amount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: startDate
    }
    notifications: toObject(concat(actualNotifications, forecastNotifications), item => item.key, item => item.value)
  }
}
