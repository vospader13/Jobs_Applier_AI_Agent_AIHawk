import time
import urllib
from pathlib import Path

import undetected_chromedriver as uc

from src.logging import logger

CHROME_PROFILE_DIR = Path("D:/Repos/Jobs_Applier_AI_Agent_AIHawk/chrome_profile")


def chrome_browser_options():
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-extensions")
    options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
    # Do NOT add --incognito -- persistent profile required
    return options


def init_browser() -> uc.Chrome:
    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        options = chrome_browser_options()
        driver = uc.Chrome(options=options)
        logger.debug("Chrome browser (undetected) initialized with persistent profile.")
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize browser: {str(e)}")
        raise RuntimeError(f"Failed to initialize browser: {str(e)}")


def HTML_to_PDF(html_content, driver):
    """
    Converte una stringa HTML in un PDF e restituisce il PDF come stringa base64.

    :param html_content: Stringa contenente il codice HTML da convertire.
    :param driver: Istanza del WebDriver di Selenium.
    :return: Stringa base64 del PDF generato.
    :raises ValueError: Se l'input HTML non e' una stringa valida.
    :raises RuntimeError: Se si verifica un'eccezione nel WebDriver.
    """
    # Validazione del contenuto HTML
    if not isinstance(html_content, str) or not html_content.strip():
        raise ValueError("Il contenuto HTML deve essere una stringa non vuota.")

    # Codifica l'HTML in un URL di tipo data
    encoded_html = urllib.parse.quote(html_content)
    data_url = f"data:text/html;charset=utf-8,{encoded_html}"

    try:
        driver.get(data_url)
        # Attendi che la pagina si carichi completamente
        time.sleep(2)  # Potrebbe essere necessario aumentare questo tempo per HTML complessi

        # Esegue il comando CDP per stampare la pagina in PDF
        pdf_base64 = driver.execute_cdp_cmd("Page.printToPDF", {
            "printBackground": True,
            "landscape": False,
            "paperWidth": 8.27,
            "paperHeight": 11.69,
            "marginTop": 0.8,
            "marginBottom": 0.8,
            "marginLeft": 0.5,
            "marginRight": 0.5,
            "displayHeaderFooter": False,
            "preferCSSPageSize": True,
            "generateDocumentOutline": False,
            "generateTaggedPDF": False,
            "transferMode": "ReturnAsBase64"
        })
        return pdf_base64['data']
    except Exception as e:
        logger.error(f"Si e' verificata un'eccezione WebDriver: {e}")
        raise RuntimeError(f"Si e' verificata un'eccezione WebDriver: {e}")
