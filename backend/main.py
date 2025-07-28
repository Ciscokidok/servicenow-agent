from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import aiohttp
import json
import logging
from typing import Dict, Any
import openai
from datetime import datetime, timedelta
import re

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

# ServiceNow configuration
SNOW_API_BASE = os.getenv('SNOW_INSTANCE')
SNOW_USERNAME = os.getenv('SNOW_USERNAME')
SNOW_PASSWORD = os.getenv('SNOW_PASSWORD')

# Validate required environment variables
if not all([SNOW_API_BASE, SNOW_USERNAME, SNOW_PASSWORD]):
    raise ValueError("Missing required ServiceNow environment variables")

# Add .service-now.com suffix if not present
if not SNOW_API_BASE.endswith('.service-now.com'):
    SNOW_API_BASE = f"{SNOW_API_BASE}.service-now.com"



TABLE_MAPPINGS = {
    "incident": "incident",
    "problem": "problem",
    "change": "change_request",
    "change request": "change_request",
    "change requests": "change_request"
}


# State mappings
STATE_MAPPINGS = {
    "incident": {
        "new": "1",
        "active": "2",
        "pending": "3"
    },
    "problem": {
        "new": "1",
        "known_error": "2",
        "resolved": "3",
        "closed": "4"
    },
    "change": {
        "new": "1",
        "planned": "2",
        "scheduled": "3",
        "implemented": "4"
    }
}

def format_date(date_str: str) -> str:
    """Format date string for ServiceNow API"""
    try:
        # Try different date formats
        for format_str in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
            try:
                date_obj = datetime.strptime(date_str, format_str)
                return date_obj.strftime("%Y-%m-%d")
            except ValueError:
                continue
        raise ValueError(f"Invalid date format: {date_str}")
    except Exception as e:
        logger.error(f"Error formatting date: {e}")
        raise ValueError(f"Invalid date format: {date_str}")



async def search_tickets_by_state(table_name: str, max_results: int = 100):
    try:
        # For change requests, use a specific query to get all records
        if table_name == "change_request":
            query = "ORDERBYdescopened_at"  # Sort by opened date, descending
        else:
            query = ""  # Empty query for other ticket types
        
        # Construct the full API URL
        SNOW_API_URL = f"https://{SNOW_API_BASE}/api/now/table/{table_name}"
        
        # Add query parameters
        params = {
            "sysparm_query": query,
            "sysparm_limit": str(max_results),
            "sysparm_sortby_desc": "sys_created_at"
        }
        
        # Log the full request details
        logger.info(f"Searching {table_name} at URL: {SNOW_API_URL}")
        logger.info(f"Request parameters: {params}")
        
        # Make the API call
        async with aiohttp.ClientSession() as session:
            async with session.get(SNOW_API_URL, params=params, auth=aiohttp.BasicAuth(SNOW_USERNAME, SNOW_PASSWORD)) as response:
                logger.info(f"Response status: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Raw response: {result}")
                    logger.info(f"Received {len(result.get('result', []))} records")
                    return {"success": True, "data": result.get("result", [])}
                else:
                    error_text = await response.text()
                    logger.error(f"ServiceNow API error: {error_text}")
                    return {"success": False, "error": error_text}
    except Exception as e:
        logger.error(f"Error searching tickets: {e}")
        return {"success": False, "error": str(e)}

async def search_tickets_by_number(table_name: str, ticket_number: str, max_results: int = 100):
    try:
        # Construct the full API URL
        SNOW_API_URL = f"https://{SNOW_API_BASE}/api/now/table/{table_name}"
        
        # Add query parameters
        params = {
            "sysparm_query": f"number={ticket_number}",
            "sysparm_limit": str(max_results),
            "sysparm_sortby_desc": "sys_created_at"
        }
        
        # Log the query parameters
        logger.info(f"Searching for ticket number: {ticket_number}")
        logger.info(f"Request parameters: {params}")
        
        # Make the API call
        async with aiohttp.ClientSession() as session:
            async with session.get(SNOW_API_URL, params=params, auth=aiohttp.BasicAuth(SNOW_USERNAME, SNOW_PASSWORD)) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Found {len(result.get('result', []))} matching records")
                    return {"success": True, "data": result.get("result", [])}
                else:
                    error_text = await response.text()
                    logger.error(f"ServiceNow API error: {error_text}")
                    return {"success": False, "error": error_text}
    except Exception as e:
        logger.error(f"Error searching tickets: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/search_snow")
async def search_snow(search_query: str, max_results: int = 100):
    try:
        logger.info(f"Received search request: {search_query}")
        
        # Extract table type
        table_name = None
        if "change request" in search_query.lower():
            table_name = "change_request"
        elif "change" in search_query.lower():
            table_name = "change_request"
        else:
            for table_type in TABLE_MAPPINGS:
                if table_type in search_query.lower():
                    table_name = TABLE_MAPPINGS[table_type]
                    break
        
        if not table_name:
            return {"success": False, "error": "Please specify ticket type (incident, problem, or change)"}
        
        # Try to extract ticket number
        ticket_number = extract_ticket_number(search_query)
        
        # If ticket number is found, search by number
        if ticket_number:
            return await search_tickets_by_number(table_name, ticket_number, max_results)
        
        # Try to extract date
        date_str = extract_date_from_query(search_query)
        
        # If no date is provided, return all tickets of that type
        if not date_str:
            return await search_tickets_by_state(table_name, max_results)
        
        # If date is provided, search for tickets created on that date
        return await search_tickets_by_date(table_name, date_str, max_results)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {"success": False, "error": str(e)}

def extract_date_from_query(query: str) -> str:
    """Extract date from query string"""
    try:
        # Remove common words that might interfere with date extraction
        cleaned_query = query.lower()
        for word in ["on", "in", "at", "the"]:
            cleaned_query = cleaned_query.replace(word, "")
        
        # Try different date patterns
        patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{1,2}/\d{1,2}/\d{4}',  # MM/DD/YYYY
            r'\d{1,2}-\d{1,2}-\d{4}',  # MM-DD-YYYY
            r'\d{1,2}\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}',  # 1 January 2025
            r'\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}'  # 1 Jan 2025
        ]
        
        for pattern in patterns:
            match = re.search(pattern, cleaned_query, re.IGNORECASE)
            if match:
                date_str = match.group(0)
                
                # Handle month names
                if any(month in date_str.lower() for month in ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]):
                    # Convert month names to numbers
                    month_map = {
                        "jan": "01", "january": "01",
                        "feb": "02", "february": "02",
                        "mar": "03", "march": "03",
                        "apr": "04", "april": "04",
                        "may": "05",
                        "jun": "06", "june": "06",
                        "jul": "07", "july": "07",
                        "aug": "08", "august": "08",
                        "sep": "09", "september": "09",
                        "oct": "10", "october": "10",
                        "nov": "11", "november": "11",
                        "dec": "12", "december": "12"
                    }
                    parts = date_str.lower().split()
                    month = month_map[parts[1]]
                    day = parts[0].zfill(2)
                    year = parts[2]
                    date_str = f"{year}-{month}-{day}"
                
                # Handle MM-DD-YYYY format
                if "-" in date_str and "/" not in date_str:
                    parts = date_str.split("-")
                    date_str = f"{parts[2]}-{parts[0]}-{parts[1]}"
                
                return date_str
        
        return None  # No date found
    except Exception as e:
        logger.error(f"Error extracting date: {e}")
        return None

def extract_ticket_number(query: str) -> str:
    """Extract ticket number from query"""
    try:
        # Look for patterns like CHG123456 or CHG-123456
        patterns = [
            r'CHG\d+',  # CHG123456
            r'CHG-\d+',  # CHG-123456
            r'CHG\d+-\d+'  # CHG123-456
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                return match.group(0)
        
        return None
    except Exception as e:
        logger.error(f"Error extracting ticket number: {e}")
        return None

async def search_tickets_by_date(table_name: str, date_str: str, max_results: int = 100):
    try:
        # Format the date for ServiceNow
        date_str = date_str.strip()
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        
        # Create a date range query for the entire day
        start_date = date_obj.strftime("%Y-%m-%d")
        end_date = (date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Get open states for this table type
        states = STATE_MAPPINGS.get(table_name, {}).values()
        state_query = "^OR".join([f"state={state}" for state in states])
        
        # Construct the query with date range using sys_created_at field
        query = f"{state_query}^sys_created_atBETWEENjavascript:gs.dateGenerate('{start_date}')@javascript:gs.dateGenerate('{end_date}')"
        
        # For change requests, add additional state filters
        if table_name == "change_request":
            query += "^state!=closed^state!=cancelled"
        
        # Construct the full API URL
        SNOW_API_URL = f"https://{SNOW_API_BASE}/api/now/table/{table_name}"
        
        # Add query parameters
        params = {
            "sysparm_query": query,
            "sysparm_limit": str(max_results),
            "sysparm_sortby_desc": "sys_created_at"
        }
        
        # Make the API call
        async with aiohttp.ClientSession() as session:
            async with session.get(SNOW_API_URL, params=params, auth=aiohttp.BasicAuth(SNOW_USERNAME, SNOW_PASSWORD)) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "data": result.get("result", [])}
                else:
                    error_text = await response.text()
                    logger.error(f"ServiceNow API error: {error_text}")
                    return {"success": False, "error": error_text}
    except Exception as e:
        logger.error(f"Error searching tickets: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/search_snow")
async def search_snow(search_query: str, max_results: int = 100):
    try:
        logger.info(f"Received search request: {search_query}")
        
        # Extract table type
        table_name = None
        for table_type in TABLE_MAPPINGS:
            if table_type in search_query.lower():
                table_name = TABLE_MAPPINGS[table_type]
                break
        
        if not table_name:
            return {"success": False, "error": "Please specify ticket type (incident, problem, or change)"}
        
        # Try to extract date
        date_str = extract_date_from_query(search_query)
        
        # If no date is provided, return all open tickets
        if not date_str:
            return await search_tickets_by_state(table_name, max_results)
        
        # If date is provided, search for tickets created on that date
        return await search_tickets_by_date(table_name, date_str, max_results)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {"success": False, "error": str(e)}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
