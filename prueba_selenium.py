from selenium import webdriver
from selenium.webdriver.common.by import By

# Inicializa el navegador
driver = webdriver.Chrome()

# Abre la página que contiene el valor RSSI
driver.get("192.168.51.43")

# Encuentra el elemento que contiene el valor RSSI
rssi_element = driver.find_element(By.ID, "RSS")  # Ajusta el selector según tu HTML

# Extrae el texto y convierte a número
rssi_value = float(rssi_element.text.replace("dBm", "").strip())

# Valida el rango
if rssi_value > -56:
    print("✅ RSSI está dentro del rango aceptable.")
else:
    print("❌ RSSI está por debajo del umbral permitido.")

# Cierra el navegador
driver.quit()
