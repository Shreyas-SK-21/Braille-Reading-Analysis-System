#include <Arduino.h>
#include "WiFi.h"
#include "esp_bt.h"

#define TX_COUNT 7
#define RX_COUNT 7
#define SAMPLE_COUNT 30
#define PWM_PIN 14

// TX multiplexer select pins
const int TX_S0 = 4;
const int TX_S1 = 5;
const int TX_S2 = 18;

// RX ADC pins
const int rxPins[RX_COUNT] =
{
  32,
  33,
  34,
  35,
  25,
  36,
  39
};

int touchMatrix[TX_COUNT][RX_COUNT];

hw_timer_t *timer = NULL;
volatile bool state = false;


// ---------- PWM INTERRUPT ----------
void IRAM_ATTR onTimer()
{
  state = !state;
  digitalWrite(PWM_PIN, state);
}


// ---------- SELECT TX CHANNEL ----------
void setTX(int ch)
{
  digitalWrite(TX_S0, ch & 1);
  digitalWrite(TX_S1, (ch >> 1) & 1);
  digitalWrite(TX_S2, (ch >> 2) & 1);
}


// ---------- START ~100kHz SIGNAL ----------
void startSignal()
{
  pinMode(PWM_PIN, OUTPUT);

  timer = timerBegin(1000000);  // 1 MHz timer
  timerAttachInterrupt(timer, &onTimer);

  // toggle every 5 µs -> 100 kHz square wave
  timerAlarm(timer, 5, true, 0);
}


// ---------- FILTERED ADC READ ----------
int readFilteredADC(int pin)
{
  int sum = 0;

  // throw away first sample (ADC capacitor settling)
  analogRead(pin);

  for(int i = 0; i < SAMPLE_COUNT; i++)
  {
    sum += analogRead(pin);
    delayMicroseconds(5);
  }

  return sum / SAMPLE_COUNT;
}


void setup()
{
  Serial.begin(115200);
  WiFi.mode(WIFI_OFF);
  btStop();

  pinMode(TX_S0, OUTPUT);
  pinMode(TX_S1, OUTPUT);
  pinMode(TX_S2, OUTPUT);

  for(int i = 0; i < RX_COUNT; i++)
  {
    pinMode(rxPins[i], INPUT);
  }

  analogSetWidth(12);
  analogSetAttenuation(ADC_11db);

  startSignal();
}


void loop()
{
  for(int tx = 0; tx < TX_COUNT; tx++)
  {
    setTX(tx);

    // allow mux + RC network to settle
    delayMicroseconds(25);

    for(int rx = 0; rx < RX_COUNT; rx++)
    {
      touchMatrix[tx][rx] = readFilteredADC(rxPins[rx]);
    }
  }

  // print matrix with per-row XOR checksum
  // Format: v0 \t v1 \t ... v6 \t CHK\n
  // CHK = XOR of the integer byte values of v0..v6 (each clamped 0-255)
  for(int tx = 0; tx < TX_COUNT; tx++)
  {
    uint8_t chk = 0;
    for(int rx = 0; rx < RX_COUNT; rx++)
    {
      int v = touchMatrix[tx][rx];
      Serial.print(v);
      Serial.print("\t");
      chk ^= (uint8_t)(v & 0xFF);
    }
    // Append checksum as last tab-separated field on the row
    Serial.print("CHK");
    Serial.print(chk);
    Serial.println();
  }
  Serial.println();
}
