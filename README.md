**Project Overview**

This project is a web scraping application designed to extract reviews from e-commerce websites. The application uses a combination of traditional web scraping techniques and Large Language Model (LLM) based extraction methods to extract reviews from websites.

**Solution Approach**

The solution approach involves the following steps:

1. **Web Scraping**: The application uses a web scraping library to extract HTML content from the target website.
2. **LLM-Based Extraction**: The application uses a Large Language Model (LLM) to extract reviews from the HTML content.
3. **Review Processing**: The extracted reviews are processed to remove duplicates and irrelevant information.
4. **API**: The processed reviews are stored in a database and made available through a RESTful API.

**System Architecture**

The system architecture is illustrated in the following diagram:

```
+---------------+
|  Web Scraper  |
+---------------+
       |
       |
       v
+---------------+
|  LLM-Based    |
|  Extraction    |
+---------------+
       |
       |
       v
+---------------+
|  Review Processing|
+---------------+
       |
       |
       v
+---------------+
|  API          |
+---------------+
```

**Workflow**

The workflow is illustrated in the following diagram:

```
+---------------+
|  User Request  |
+---------------+
       |
       |
       v
+---------------+
|  API Request   |
+---------------+
       |
       |
       v
+---------------+
|  Review Retrieval|
+---------------+
       |
       |
       v
+---------------+
|  Review Processing|
+---------------+
       |
       |
       v
+---------------+
|  API Response  |
+---------------+
```

**Instructions on How to Run the Project**

To run the project, follow these steps:

1. Clone the repository using the following command:
```bash
git clone https://github.com/AditiPrabhuA/gomarble.git
```
2. Install the required dependencies using the following command:
```bash
pip install -r requirements.txt
```
3. Run the application using the following commands:
```bash
python backend/app.py
python frontend/npm run dev
ollama serve
```
4. Open a web browser and navigate to `http://localhost:3000` to access the frontend.

**API Usage**

The API provides the following endpoint:
* `GET /api/reviews`: Retrieves a list of reviews.
