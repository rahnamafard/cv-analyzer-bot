import google.generativeai as genai
import logging
import re
import time
import random
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class CVAnalyzer:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        # Use 'gemini-pro-vision' for image processing
        self.model = genai.GenerativeModel('gemini-pro-vision')

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((Exception, httpx.ConnectError)),
        reraise=True
    )
    def _generate_content(self, prompt, pdf_content):
        logger.debug("Sending request to Gemini API...")
        try:
            response = self.model.generate_content([
                prompt,
                {"mime_type": "application/pdf", "data": pdf_content}
            ])
            logger.debug(f"Received response from Gemini API. Response type: {type(response)}")
            return response
        except Exception as e:
            logger.error(f"Error in API call: {str(e)}")
            raise  # Re-raise the exception to trigger a retry

    def analyze_cv(self, pdf_file):
        try:
            # Read the PDF file as bytes
            pdf_content = pdf_file.read()

            prompt = """Analyze the attached resume and provide detailed feedback. 
            Use the exact format provided below, including the section titles:

            نقاط قوت رزومه:

            • [Strength point 1]
            • [Strength point 2]
            • [Strength point 3]
            ...

            زمینه‌های نیازمند بهبود:

            • [Improvement area 1]
            • [Improvement area 2]
            • [Improvement area 3]
            ...

            پیشنهادات برای بهبود رزومه:

            • [Suggestion 1]
            • [Suggestion 2]
            • [Suggestion 3]
            ...

            نمونه‌های بهبود یافته:

            • [Section Name 1]:

            نسخه اصلی:
            [Original text in the original language]
            نسخه بهبود یافته:
            [Improved version in the EXACT SAME LANGUAGE as the original]

            • [Section Name 2]:

            نسخه اصلی:
            [Original text in the original language]
            نسخه بهبود یافته:
            [Improved version in the EXACT SAME LANGUAGE as the original]

            • [Section Name 3]:
            
            نسخه اصلی:
            [Original text in the original language]
            نسخه بهبود یافته:
            [Improved version in the EXACT SAME LANGUAGE as the original]

            موقعیت‌های شغلی مرتبط:

            • [Related Job Position 1 in English]
            • [Related Job Position 2 in English]
            • [Related Job Position 3 in English]
            • [Related Job Position 4 in English]
            • [Related Job Position 5 in English]

            Ensure that you provide at least 3 points for each section. Use bullet points (•) for each item in all sections.
            IMPORTANT: The improved versions MUST be in the EXACT SAME LANGUAGE as the original resume. If the original is in English, the improved version should be in English. If the original is in Persian, the improved version should be in Persian.
            All other feedback sections (نقاط قوت رزومه, زمینه‌های نیازمند بهبود, پیشنهادات برای بهبود رزومه) should be in Persian.
            The "موقعیت‌های شغلی مرتبط" section MUST be in English, using standard job titles.
            Do not include any additional text or explanations outside of these sections.
            """

            response = self._generate_content(prompt, pdf_content)
            
            if response.text.strip():
                logger.debug(f"Gemini API response text: {response.text}")
                job_positions = self.extract_job_positions(response.text)
                formatted_response = self.format_response(response.text)
                print(f"Extracted job positions: {job_positions}")  # Debugging line
                return formatted_response, job_positions
            else:
                logger.error(f"Unexpected or empty response from Gemini API: {response}")
                return "متأسفانه، تحلیل رزومه با مشکل مواجه شد. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.", []

        except Exception as e:
            logger.exception(f"Error in analyze_cv: {str(e)}")
            return f"متأسفانه خطایی در هنگام تحلیل رزومه شما رخ داد:\n\n{str(e)}\n\nلطفاً بعداً دوباره تلاش کنید یا در صورت تداوم مشکل با پشتیبانی تماس بگیرید.", []

    def extract_job_positions(self, text):
        lines = text.split('\n')
        job_positions = []
        capture = False
        for line in lines:
            if 'موقعیت‌های شغلی مرتبط:' in line:
                capture = True
                continue
            if capture and line.strip().startswith('•'):
                position = line.strip()[1:].strip()
                # Ensure the position is in English
                if all(ord(char) < 128 for char in position):
                    job_positions.append(position)
            elif capture and line.strip() and not line.strip().startswith('•'):
                break
        print(f"Extracted job positions in method: {job_positions}")  # Debugging line
        return job_positions

    def format_response(self, text):
        # Add a header and footer
        header = "*📄 تحلیل رزومه 📄*\n\n"
        footer = "\n\nبرای بهبود رزومه خود، این پیشنهادات را در نظر بگیرید\\. موفق باشید\\! 🌟"
        
        # Process the text line by line
        lines = text.split('\n')
        processed_lines = []
        for line in lines:
            if line.startswith('##'):
                # Replace '##' with emoji and make the line bold
                line = f"*📌 {self.escape_markdown(line[2:].strip())}*"
            elif line.startswith('نقاط قوت رزومه:') or line.startswith('زمینه‌های نیازمند بهبود:') or line.startswith('پیشنهادات برای بهبود رزومه:') or line.startswith('نمونه‌های بهبود یافته:'):
                # Make main headings bold
                line = f"*{self.escape_markdown(line)}*"
            elif line.strip().startswith('•'):
                # Handle bullet points with bold titles
                match = re.match(r'(•\s+)(\*\*.*?\*\*)(.*)', line)
                if match:
                    bullet, title, rest = match.groups()
                    title = title.strip('*')  # Remove asterisks
                    line = f"{self.escape_markdown(bullet)}*{self.escape_markdown(title)}*{self.escape_markdown(rest)}"
                else:
                    line = self.escape_markdown(line)
            elif line.strip() == 'نسخه بهبود یافته:':
                # Add a line break before "نسخه بهبود یافته:"
                line = f"\n{self.escape_markdown(line)}"
            else:
                line = self.escape_markdown(line)
            processed_lines.append(line)
        
        # Join the processed lines back together
        processed_text = '\n'.join(processed_lines)
        
        formatted_text = f"{header}{processed_text}{footer}"
        
        # Return text with Markdown formatting
        return formatted_text

    def escape_markdown(self, text):
        escape_chars = '_*[]()~`>#+-=|{}.!'
        return ''.join(f'\\{char}' if char in escape_chars else char for char in text)
