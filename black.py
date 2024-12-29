import os
import time
import logging
import requests
import base64
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, ElementClickInterceptedException, StaleElementReferenceException

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def create_folder(query):
    """Create a folder based on the search query."""
    folder_name = query.replace(" ", "_")  # Replace spaces with underscores for folder name
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
    return folder_name

def save_image_link(folder, img_url):
    """Save image URL to a text file in the folder."""
    with open(os.path.join(folder, "image_links.txt"), "a") as f:
        f.write(f"{img_url}\n")

def download_image(url, save_path):
    """Download image from URL or handle base64 image data."""
    if url.startswith("data:image"):
        base64_data = url.split(",")[1]
        try:
            with open(save_path, 'wb') as f:
                f.write(base64.b64decode(base64_data))
            logging.info(f"Base64 image saved to {save_path}")
        except Exception as e:
            logging.error(f"Error saving base64 image: {e}")
    else:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                logging.info(f"Image saved to {save_path}")
            else:
                logging.error(f"Failed to download {url}")
        except Exception as e:
            logging.error(f"Error downloading {url}: {e}")

def accept_google_terms(driver):
    """Handle Google's terms and conditions popups."""
    try:
        consent_button = WebDriverWait(driver, 0.1).until(
            EC.element_to_be_clickable((By.XPATH, '//*[contains(text(), "I agree") or contains(text(), "Reject all") or contains(text(), "Accept all")]'))
        )
        consent_button.click()
        logging.info("Consent popup handled.")
    except (NoSuchElementException, TimeoutException):
        logging.info("No consent popup found.")

def scroll_past_recommended_images(driver):
    """Scroll down to bypass the entire suggested image section."""
    while True:
        driver.execute_script("window.scrollBy(0, 400);")  # Scroll down by 400 pixels
        time.sleep(0.1)  # Allow some time for the page to adjust
        
        # Try to find enough valid thumbnails that are not part of the recommended section
        thumbnails = driver.find_elements(By.CSS_SELECTOR, "img.YQ4gaf")
        filtered_thumbnails = filter_thumbnails(thumbnails)
        
        if len(filtered_thumbnails) > 10:  # Assume more than 10 valid images means we're past the suggested area
            logging.info("Successfully scrolled past the recommended images section.")
            break

def filter_thumbnails(thumbnails):
    """Filter out thumbnails with 'lQHeM' class, those with 'topmargin=3', 'marginheight=3' attributes, or invalid size."""
    filtered = []
    for img in thumbnails:
        try:
            # Check the parent or grandparent elements for the 'lQHeM' class
            parent = img.find_element(By.XPATH, '..')
            grandparent = parent.find_element(By.XPATH, '..')

            # Check for deprecated attributes like 'topmargin' or 'marginheight' with value 3
            topmargin = img.get_attribute("topmargin")
            marginheight = img.get_attribute("marginheight")

            # Get the size of the thumbnail and filter out very small thumbnails
            width = img.size['width']
            height = img.size['height']

            if (
                "lQHeM" not in parent.get_attribute("class") and
                "lQHeM" not in grandparent.get_attribute("class") and
                (topmargin != "3" and marginheight != "3") and
                width > 50 and height > 50  # Ensure the thumbnail is not too small
            ):
                filtered.append(img)
            else:
                logging.info("Skipping image with 'lQHeM' class, deprecated margin attributes, or invalid size.")
        except NoSuchElementException:
            # If no parent or grandparent is found, assume it's safe
            filtered.append(img)

    logging.info(f"Filtered thumbnails: {len(filtered)} valid images remain after filtering.")
    return filtered

def is_element_in_viewport(driver, element):
    """Check if the element is within the visible viewport."""
    rect = driver.execute_script("""
        var rect = arguments[0].getBoundingClientRect();
        return {top: rect.top, left: rect.left, bottom: rect.bottom, right: rect.right, width: rect.width, height: rect.height};
    """, element)

    window_size = driver.execute_script("return [window.innerWidth, window.innerHeight];")

    is_within_bounds = (
        0 <= rect['top'] < window_size[1] and     # Top is within vertical bounds
        0 <= rect['left'] < window_size[0] and    # Left is within horizontal bounds
        rect['bottom'] <= window_size[1] and      # Bottom is within vertical bounds
        rect['right'] <= window_size[0]           # Right is within horizontal bounds
    )
    
    logging.info(f"Element bounds: {rect}, window size: {window_size}, is within bounds: {is_within_bounds}")
    
    return is_within_bounds

def click_image(driver, img_element):
    """Safely click an image element with retries and fallback to JavaScript."""
    try:
        # Ensure the element is visible by scrolling into view
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", img_element)
        time.sleep(0.1)  # Wait for the image to scroll and load properly

        # Check if the element is interactable before clicking
        if img_element.is_displayed() and img_element.is_enabled():
            img_element.click()  # Try normal click
            time.sleep(0.1)  # Wait for image to load
        else:
            logging.warning("Element not interactable, attempting JavaScript click.")
            driver.execute_script("arguments[0].click();", img_element)  # Fallback to JavaScript click
            time.sleep(0.1)
    
    except ElementClickInterceptedException:
        logging.warning("Click intercepted, retrying with JavaScript.")
        driver.execute_script("arguments[0].click();", img_element)
        time.sleep(0.1)  # Allow time for image to load
    
    except Exception as e:
        logging.error(f"Failed to click on image: {e}")

def fetch_full_res_image(driver, retry_limit=5):
    """Fetch the full-resolution image URL with retries."""
    for attempt in range(retry_limit):
        try:
            # Wait for the full-resolution image to be present
            full_res_image = WebDriverWait(driver, 0.1).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'img.sFlh5c.FyHeAf.iPVvYb, img.srp.EIlDfe'))
            )
            img_url = full_res_image.get_attribute("src")

            # Avoid empty placeholders
            if img_url and not img_url.startswith("data:image/gif"):
                return img_url
        except TimeoutException:
            logging.warning(f"Attempt {attempt + 1} to load full-resolution image failed.")
            time.sleep(0.1)  # Increased wait time before retrying
        except Exception as e:
            logging.error(f"Error fetching full-resolution image: {e}")
            break
    logging.error(f"Failed to load full-resolution image after {retry_limit} attempts.")
    return None

def click_visible_thumbnails(driver, max_images=100, folder=None):
    """Scroll to and click only thumbnails fully visible within the viewport."""
    img_count = 0
    processed_urls = set()  # Track processed thumbnails by their URL (or use a unique element identifier if available)

    while img_count < max_images:
        try:
            # Refetch thumbnails after every iteration
            thumbnails = driver.find_elements(By.CSS_SELECTOR, "img.YQ4gaf")
            filtered_thumbnails = filter_thumbnails(thumbnails)

            for index, img_element in enumerate(filtered_thumbnails):
                if img_count >= max_images:
                    break

                # Get the URL of the thumbnail image to track processed thumbnails
                img_src = img_element.get_attribute('src')
                if img_src in processed_urls:
                    logging.info(f"Skipping already processed thumbnail {index}.")
                    continue

                try:
                    # Scroll the thumbnail into view
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", img_element)
                    time.sleep(0.1)  # Wait for the image to scroll and load properly

                    # Check if the thumbnail is actually within the visible viewport
                    if is_element_in_viewport(driver, img_element):
                        logging.info(f"Thumbnail {index} is visible, attempting to click.")

                        # Try to click the thumbnail
                        click_image(driver, img_element)

                        # Attempt to fetch and download the full-resolution image
                        img_url = fetch_full_res_image(driver)
                        if img_url:
                            img_count += 1
                            logging.info(f"Downloading image {img_count}: {img_url[:30]}...")
                            image_path = os.path.join(folder, f"full_image_{img_count}.jpg")
                            download_image(img_url, image_path)
                            save_image_link(folder, img_url)  # Save the image URL in the text file
                            processed_urls.add(img_src)  # Mark the thumbnail as processed

                        # Go back to the image results
                        driver.execute_script("window.history.go(-1)")
                        time.sleep(0.1)  # Allow the page to reload after going back

                    else:
                        logging.info(f"Skipping thumbnail {index} as it's outside the visible viewport.")

                except Exception as e:
                    logging.error(f"Error interacting with thumbnail {index}: {e}")

        except Exception as e:
            logging.error(f"Error processing thumbnails: {e}")
            break

    return img_count

def perform_image_search(driver, query, max_images=4000):
    """Search Google Images, scroll past recommended images, and download full-resolution images."""
    try:
        # Create a folder to save images and image links
        folder = create_folder(query)

        # Perform search for the query
        search_box = WebDriverWait(driver, 0.1).until(EC.presence_of_element_located((By.NAME, 'q')))
        search_box.send_keys(f"{query}\n")
        logging.info(f"Performed search for: {query}")

        # Click on the "Images" tab
        images_tab = WebDriverWait(driver, 0.1).until(EC.element_to_be_clickable((By.LINK_TEXT, "Images")))
        images_tab.click()

        # Scroll down to skip recommended images
        scroll_past_recommended_images(driver)

        # Click visible thumbnails and download full images
        img_count = click_visible_thumbnails(driver, max_images, folder)

        logging.info(f"Downloaded {img_count} images.")
    except TimeoutException as e:
        logging.error(f"Error during image search: {e}")

# Main method to start the process
def main():
    driver = uc.Chrome()  # Initialize Chrome WebDriver
    try:
        driver.get("https://www.google.com")

        # Handle Google's consent popups
        accept_google_terms(driver)

        # Perform the image search and download images
        perform_image_search(driver, "black vultures in flock")

    finally:
        driver.quit()  # Ensure WebDriver is closed properly

if __name__ == "__main__":
    main()


