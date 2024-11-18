from flask import Flask, jsonify, request
from dotenv import load_dotenv
import psycopg2
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.dialects.postgresql import JSONB
from openai import OpenAI
from bs4 import BeautifulSoup
import os
import requests
import json
import re
from config import Config

load_dotenv()
openai_client = OpenAI()

application = Flask(__name__)
application.config.from_object(Config)
db = SQLAlchemy(application)

class WebsiteData(db.Model):
    __tablename__ = 'website_data'
    website = db.Column(db.String, primary_key=True, nullable=False)
    count = db.Column(db.Integer, nullable=False)
    question = db.Column(db.String, nullable=False)
    options = options = db.Column(JSONB, nullable=True)

@application.route('/get-website-data', methods=['GET'])
def get_website_data():
    questions = WebsiteData.query.all()
    return jsonify([{'website': q.website, 'count': q.count, 'question': q.question, 'options': q.options} for q in questions])

@application.route('/add-website-data', methods=['POST'])
def add_question_and_options():
    data = request.get_json()
    website = data.get('website')
    count = data.get('count')
    question = data.get('question')
    options = data.get('options')

    if not website or not question:
        return "Website and question are required", 400

    new_entry = WebsiteData(website=website, count=count, question=question, options=options)
    db.session.add(new_entry)
    db.session.commit()
    
    return "Question added successfully", 201

@application.route("/")
def hello_world():
    return "<p>Hello, World!</p>"

@application.route("/scrape", methods=['POST'])
def scrape():
    data = request.get_json()
    website_url = data.get('website')

    if not website_url.startswith(("http://", "https://")):
        website_url = "https://" + website_url

    # Query DB to check if entry with same website exists
    question_entry = WebsiteData.query.filter_by(website=website_url).first()
    
    if question_entry:
        question_entry.count += 1
        db.session.commit()

        return jsonify({
            "website": question_entry.website,
            "count": question_entry.count,
            "question": question_entry.question,
            "options": question_entry.options
        })
    else:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36"
        }
        response = requests.get(website_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")
        website_content = soup.get_text()
        
        completion = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": f"Generate an appropriate question asking for the reason for visiting this website based on the content provided e.g. 'Which product category are you interested in?', along with multiple choice options and return in a JSON object with two keys, question and options, where question is a string and options is an array of strings: {website_content}"}
            ]
        )

        response = completion.choices[0].message.content
        match = re.search(r'\{.*\}', response, re.DOTALL)
        json_string = match.group(0)
        json_object = json.loads(json_string)
        question = json_object["question"]
        optionsArray = json_object["options"]
        options = [{'option': option, 'count': 0} for option in optionsArray]

        new_entry = WebsiteData(website=website_url, count=1, question=question, options=options)
        db.session.add(new_entry)
        db.session.commit()

        return jsonify({
            "website": new_entry.website,
            "count": new_entry.count,
            "question": new_entry.question,
            "options": new_entry.options
        })

@application.route("/option-response", methods=['POST'])
def option_response():
    data = request.get_json()
    website = data.get('website')
    option = data.get('option')

    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    question_entry = WebsiteData.query.filter_by(website=website).first()

    for opt in question_entry.options:
        if opt['option'] == option:
            opt['count'] += 1
            break
    else:
        return "Option not found", 404
    
    flag_modified(question_entry, "options")
    db.session.commit()

    return jsonify({"website": question_entry.website, "options": question_entry.options})