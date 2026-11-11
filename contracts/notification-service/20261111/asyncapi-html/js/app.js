
    const schema = {
  "asyncapi": "3.0.0",
  "info": {
    "title": "Notification Service",
    "version": "1.0"
  },
  "channels": {
    "order-events": {
      "address": "order-events",
      "messages": {
        "OrderConfirmed": {
          "name": "OrderConfirmed",
          "title": "OrderConfirmed",
          "payload": {
            "$schema": "http://json-schema.org/draft/2020-12/schema#",
            "title": "OrderConfirmedEvent",
            "description": "Order confirmed: order-service consumed PaymentCaptured and moved the order to confirmed.",
            "type": "object",
            "required": [
              "orderId",
              "customerId",
              "timestamp"
            ],
            "properties": {
              "orderId": {
                "description": "Order UUID (order-service's order id).",
                "examples": [
                  "3f2b8c1e-5d4a-4e7b-9c6f-1a2b3c4d5e6f"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-2>"
              },
              "customerId": {
                "description": "Customer who placed the order.",
                "examples": [
                  "7c9e6679-7425-40de-944b-e07fc1f90ae7"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-3>"
              },
              "timestamp": {
                "description": "When the order was confirmed (ISO-8601 instant).",
                "examples": [
                  "2026-10-31T10:15:30Z"
                ],
                "type": "string",
                "format": "date-time",
                "x-parser-schema-id": "<anonymous-schema-4>"
              }
            },
            "x-parser-schema-id": "<anonymous-schema-1>"
          },
          "x-parser-unique-object-id": "OrderConfirmed"
        },
        "OrderPaymentFailed": {
          "name": "OrderPaymentFailed",
          "title": "OrderPaymentFailed",
          "payload": {
            "$schema": "http://json-schema.org/draft/2020-12/schema#",
            "title": "OrderPaymentFailedEvent",
            "description": "Payment capture failed: order-service consumed PaymentFailed and moved the order to payment_failed.",
            "type": "object",
            "required": [
              "orderId",
              "customerId",
              "reason",
              "timestamp"
            ],
            "properties": {
              "orderId": {
                "description": "Order UUID (order-service's order id).",
                "examples": [
                  "3f2b8c1e-5d4a-4e7b-9c6f-1a2b3c4d5e6f"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-6>"
              },
              "customerId": {
                "description": "Customer who placed the order.",
                "examples": [
                  "7c9e6679-7425-40de-944b-e07fc1f90ae7"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-7>"
              },
              "reason": {
                "description": "payment-service's capture-failure reason.",
                "examples": [
                  "capture_failed"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-8>"
              },
              "timestamp": {
                "description": "When the order moved to payment_failed (ISO-8601 instant).",
                "examples": [
                  "2026-10-31T10:15:30Z"
                ],
                "type": "string",
                "format": "date-time",
                "x-parser-schema-id": "<anonymous-schema-9>"
              }
            },
            "x-parser-schema-id": "<anonymous-schema-5>"
          },
          "x-parser-unique-object-id": "OrderPaymentFailed"
        },
        "OrderCancelled": {
          "name": "OrderCancelled",
          "title": "OrderCancelled",
          "payload": {
            "$schema": "http://json-schema.org/draft/2020-12/schema#",
            "title": "OrderCancelledEvent",
            "description": "Order cancelled: a customer/operator cancel or a consumed PaymentAuthorizationExpired moved the order to cancelled.",
            "type": "object",
            "required": [
              "orderId",
              "customerId",
              "timestamp"
            ],
            "properties": {
              "orderId": {
                "description": "Order UUID (order-service's order id).",
                "examples": [
                  "3f2b8c1e-5d4a-4e7b-9c6f-1a2b3c4d5e6f"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-11>"
              },
              "customerId": {
                "description": "Customer who placed the order.",
                "examples": [
                  "7c9e6679-7425-40de-944b-e07fc1f90ae7"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-12>"
              },
              "timestamp": {
                "description": "When the order was cancelled (ISO-8601 instant).",
                "examples": [
                  "2026-10-31T10:15:30Z"
                ],
                "type": "string",
                "format": "date-time",
                "x-parser-schema-id": "<anonymous-schema-13>"
              },
              "reason": {
                "description": "Cancellation trigger: customer | auth_expired | stale | operator.",
                "examples": [
                  "customer"
                ],
                "type": [
                  "string",
                  "null"
                ],
                "x-parser-schema-id": "<anonymous-schema-14>"
              },
              "actor": {
                "description": "Who cancelled; absent on pre-v3 messages.",
                "type": [
                  "object",
                  "null"
                ],
                "required": [
                  "type",
                  "id"
                ],
                "properties": {
                  "type": {
                    "description": "Actor type: customer | operator | system.",
                    "examples": [
                      "operator"
                    ],
                    "type": "string",
                    "x-parser-schema-id": "<anonymous-schema-16>"
                  },
                  "id": {
                    "description": "Actor id: the customerId, operator id, or system component.",
                    "examples": [
                      "dev-operator"
                    ],
                    "type": "string",
                    "x-parser-schema-id": "<anonymous-schema-17>"
                  }
                },
                "x-parser-schema-id": "<anonymous-schema-15>"
              }
            },
            "x-parser-schema-id": "<anonymous-schema-10>"
          },
          "x-parser-unique-object-id": "OrderCancelled"
        }
      },
      "x-parser-unique-object-id": "order-events"
    },
    "user-events": {
      "address": "user-events",
      "messages": {
        "UserRegistered": {
          "name": "UserRegistered",
          "title": "UserRegistered",
          "payload": {
            "$schema": "http://json-schema.org/draft/2020-12/schema#",
            "title": "UserRegisteredEvent",
            "description": "New user signed up: POST /auth/signup succeeded.",
            "type": "object",
            "required": [
              "userId",
              "email"
            ],
            "properties": {
              "userId": {
                "description": "User UUID. Also the partition key.",
                "examples": [
                  "5b6c7d8e-9f0a-4b1c-8d2e-3f4a5b6c7d8e"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-19>"
              },
              "email": {
                "description": "User's email address.",
                "examples": [
                  "jane@example.com"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-20>"
              }
            },
            "x-parser-schema-id": "<anonymous-schema-18>"
          },
          "x-parser-unique-object-id": "UserRegistered"
        }
      },
      "x-parser-unique-object-id": "user-events"
    },
    "fulfilment-events": {
      "address": "fulfilment-events",
      "messages": {
        "DispatchConfirmed": {
          "name": "DispatchConfirmed",
          "title": "DispatchConfirmed",
          "payload": {
            "$schema": "http://json-schema.org/draft/2020-12/schema#",
            "title": "DispatchConfirmedEvent",
            "description": "Order dispatched: pick/pack/dispatch succeeded. Carries a full item snapshot so consumers need no order lookup.",
            "type": "object",
            "required": [
              "orderId",
              "trackingNo"
            ],
            "properties": {
              "orderId": {
                "description": "Order UUID (order-service's order id).",
                "examples": [
                  "3f2b8c1e-5d4a-4e7b-9c6f-1a2b3c4d5e6f"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-22>"
              },
              "trackingNo": {
                "description": "Carrier tracking number.",
                "examples": [
                  "TRK-123456789"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-23>"
              },
              "items": {
                "description": "Items dispatched. Always sent.",
                "type": "array",
                "items": {
                  "type": "object",
                  "required": [
                    "sku",
                    "productName",
                    "quantity",
                    "unitPriceCents"
                  ],
                  "properties": {
                    "sku": {
                      "description": "Product SKU.",
                      "examples": [
                        "SKU-0042"
                      ],
                      "type": "string",
                      "x-parser-schema-id": "<anonymous-schema-26>"
                    },
                    "productName": {
                      "description": "Product name at dispatch time.",
                      "examples": [
                        "Espresso cup"
                      ],
                      "type": "string",
                      "x-parser-schema-id": "<anonymous-schema-27>"
                    },
                    "quantity": {
                      "description": "Units dispatched.",
                      "examples": [
                        2
                      ],
                      "type": "integer",
                      "format": "int32",
                      "x-parser-schema-id": "<anonymous-schema-28>"
                    },
                    "unitPriceCents": {
                      "description": "Unit price, in cents.",
                      "examples": [
                        1250
                      ],
                      "type": "integer",
                      "format": "int32",
                      "x-parser-schema-id": "<anonymous-schema-29>"
                    }
                  },
                  "x-parser-schema-id": "<anonymous-schema-25>"
                },
                "x-parser-schema-id": "<anonymous-schema-24>"
              }
            },
            "x-parser-schema-id": "<anonymous-schema-21>"
          },
          "x-parser-unique-object-id": "DispatchConfirmed"
        },
        "DispatchFailed": {
          "name": "DispatchFailed",
          "title": "DispatchFailed",
          "payload": {
            "$schema": "http://json-schema.org/draft/2020-12/schema#",
            "title": "DispatchFailedEvent",
            "description": "Dispatch failed: pick/pack/dispatch hit an error. payment-service voids the hold; order-service marks the order failed.",
            "type": "object",
            "required": [
              "orderId",
              "reason"
            ],
            "properties": {
              "orderId": {
                "description": "Order UUID (order-service's order id).",
                "examples": [
                  "3f2b8c1e-5d4a-4e7b-9c6f-1a2b3c4d5e6f"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-31>"
              },
              "reason": {
                "description": "Why dispatch failed.",
                "examples": [
                  "carrier_unavailable"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-32>"
              }
            },
            "x-parser-schema-id": "<anonymous-schema-30>"
          },
          "x-parser-unique-object-id": "DispatchFailed"
        }
      },
      "x-parser-unique-object-id": "fulfilment-events"
    },
    "payment-events": {
      "address": "payment-events",
      "messages": {
        "PaymentCaptured": {
          "name": "PaymentCaptured",
          "title": "PaymentCaptured",
          "payload": {
            "$schema": "http://json-schema.org/draft/2020-12/schema#",
            "title": "PaymentCapturedEvent",
            "description": "Money moved: capture succeeded after DispatchConfirmed. Published once per order.",
            "type": "object",
            "required": [
              "orderId",
              "amountCents",
              "timestamp"
            ],
            "properties": {
              "orderId": {
                "description": "Order UUID (order-service's order id).",
                "examples": [
                  "3f2b8c1e-5d4a-4e7b-9c6f-1a2b3c4d5e6f"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-34>"
              },
              "amountCents": {
                "description": "Amount captured, in cents.",
                "examples": [
                  4999
                ],
                "type": "integer",
                "format": "int32",
                "x-parser-schema-id": "<anonymous-schema-35>"
              },
              "timestamp": {
                "description": "When the capture happened (ISO-8601 instant).",
                "examples": [
                  "2026-10-31T10:15:30Z"
                ],
                "type": "string",
                "format": "date-time",
                "x-parser-schema-id": "<anonymous-schema-36>"
              }
            },
            "x-parser-schema-id": "<anonymous-schema-33>"
          },
          "x-parser-unique-object-id": "PaymentCaptured"
        },
        "PaymentFailed": {
          "name": "PaymentFailed",
          "title": "PaymentFailed",
          "payload": {
            "$schema": "http://json-schema.org/draft/2020-12/schema#",
            "title": "PaymentFailedEvent",
            "description": "Capture declined after DispatchConfirmed. Authorize declines are synchronous and publish nothing.",
            "type": "object",
            "required": [
              "orderId",
              "paymentId",
              "amountCents",
              "reason",
              "timestamp"
            ],
            "properties": {
              "orderId": {
                "description": "Order UUID (order-service's order id).",
                "examples": [
                  "3f2b8c1e-5d4a-4e7b-9c6f-1a2b3c4d5e6f"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-38>"
              },
              "paymentId": {
                "description": "payment-service's own Payment id, for log/trace correlation only.",
                "examples": [
                  "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-39>"
              },
              "amountCents": {
                "description": "Amount that failed to charge, in cents.",
                "examples": [
                  4999
                ],
                "type": "integer",
                "format": "int32",
                "x-parser-schema-id": "<anonymous-schema-40>"
              },
              "reason": {
                "description": "Failure reason.",
                "examples": [
                  "capture_failed"
                ],
                "type": "string",
                "x-parser-schema-id": "<anonymous-schema-41>"
              },
              "timestamp": {
                "description": "When the capture was declined (ISO-8601 instant).",
                "examples": [
                  "2026-10-31T10:15:30Z"
                ],
                "type": "string",
                "format": "date-time",
                "x-parser-schema-id": "<anonymous-schema-42>"
              }
            },
            "x-parser-schema-id": "<anonymous-schema-37>"
          },
          "x-parser-unique-object-id": "PaymentFailed"
        }
      },
      "x-parser-unique-object-id": "payment-events"
    }
  },
  "operations": {
    "order-events": {
      "action": "receive",
      "channel": "$ref:$.channels.order-events",
      "messages": [
        "$ref:$.channels.order-events.messages.OrderConfirmed",
        "$ref:$.channels.order-events.messages.OrderPaymentFailed",
        "$ref:$.channels.order-events.messages.OrderCancelled"
      ],
      "x-parser-unique-object-id": "order-events"
    },
    "user-events": {
      "action": "receive",
      "channel": "$ref:$.channels.user-events",
      "messages": [
        "$ref:$.channels.user-events.messages.UserRegistered"
      ],
      "x-parser-unique-object-id": "user-events"
    },
    "fulfilment-events": {
      "action": "receive",
      "channel": "$ref:$.channels.fulfilment-events",
      "messages": [
        "$ref:$.channels.fulfilment-events.messages.DispatchConfirmed",
        "$ref:$.channels.fulfilment-events.messages.DispatchFailed"
      ],
      "x-parser-unique-object-id": "fulfilment-events"
    },
    "payment-events": {
      "action": "receive",
      "channel": "$ref:$.channels.payment-events",
      "messages": [
        "$ref:$.channels.payment-events.messages.PaymentCaptured",
        "$ref:$.channels.payment-events.messages.PaymentFailed"
      ],
      "x-parser-unique-object-id": "payment-events"
    }
  },
  "x-parser-spec-parsed": true,
  "x-parser-api-version": 3,
  "x-parser-spec-stringified": true
};
    const config = {"show":{"sidebar":true},"sidebar":{"showOperations":"byDefault"}};
    const appRoot = document.getElementById('root');
    AsyncApiStandalone.render(
        { schema, config, }, appRoot
    );
  