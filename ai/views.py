import os
import re
import json
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
from datetime import datetime
import tempfile
from werkzeug.utils import secure_filename
from docx import Document
from dotenv import load_dotenv
import difflib
from typing import List, Dict, Tuple
import io
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework import status
from django.utils.timezone import now
# Load environment variables
import google.generativeai as genai
from google.generativeai import get_model
load_dotenv()

# Configure Gemini AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY not found in environment variables. Please add it to your .env file.")
else:
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Try to find and set the model
    try:
        # First, list models to see what's available and their exact names
        available_models = [m.name for m in genai.list_models()]
        print("Available Gemini models:")
        for m_name in available_models:
            print(f"- {m_name}")

        # Try to get 'gemini-1.5-flash', preferring the 'models/' prefix
        if 'models/gemini-1.5-flash' in available_models:
            model = genai.get_model('models/gemini-1.5-flash')
            print("Successfully initialized model: models/gemini-1.5-flash")
        elif 'gemini-1.5-flash' in available_models: # Fallback, less common to omit 'models/' for get_model
            model = genai.get_model('gemini-1.5-flash')
            print("Successfully initialized model: gemini-1.5-flash (without models/ prefix)")
        else:
            # If 'gemini-1.5-flash' isn't found, try a common alternative or 'gemini-pro'
            if 'models/gemini-1.5-flash-001' in available_models:
                model = genai.get_model('models/gemini-1.5-flash-001')
                print("Successfully initialized model: models/gemini-1.5-flash-001")
            elif 'models/gemini-pro' in available_models:
                model = genai.get_model('models/gemini-pro')
                print("Successfully initialized model: models/gemini-pro (as fallback)")
            else:
                print("Warning: Neither 'gemini-1.5-flash' nor 'gemini-pro' found. AI features will be limited.")
                model = None

    except Exception as e:
        print(f"Error initializing Gemini model with API key: {e}")
        model = None

# Essay type classifications
ESSAY_TYPES = {
    'argumentative': {
        'keywords': ['argue', 'thesis', 'evidence', 'counterargument', 'claim', 'support', 'oppose', 'debate'],
        'criteria': [
            'Clear thesis statement',
            'Strong evidence and examples',
            'Counterargument acknowledgment',
            'Logical flow of arguments',
            'Source credibility check'
        ]
    },
    'narrative': {
        'keywords': ['story', 'experience', 'happened', 'remember', 'narrative', 'personal', 'journey'],
        'criteria': [
            'Clear narrative arc',
            'Vivid imagery and descriptions',
            'Dialogue quality',
            'Character development',
            'Chronological flow'
        ]
    },
    'literary_analysis': {
        'keywords': ['analyze', 'literary', 'author', 'character', 'theme', 'symbolism', 'literary device'],
        'criteria': [
            'Present tense usage',
            'Proper title italicization',
            'Quote integration',
            'Literary device identification',
            'Theme analysis depth'
        ]
    },
    'expository': {
        'keywords': ['explain', 'inform', 'describe', 'process', 'how to', 'definition'],
        'criteria': [
            'Clear explanations',
            'Logical organization',
            'Supporting details',
            'Objective tone',
            'Factual accuracy'
        ]
    }
}

class DocumentProcessor:
    @staticmethod
    def read_docx(file_path):
        try:
            doc = Document(file_path)
            paragraphs = []
            for para in doc.paragraphs:
                if para.text.strip():
                    paragraphs.append(para.text.strip())
            return {
                'text': '\n\n'.join(paragraphs),
                'paragraphs': paragraphs,
                'paragraph_count': len(paragraphs)
            }
        except Exception as e:
            raise Exception(f"Error reading DOCX file: {str(e)}")
    
    @staticmethod
    def read_txt(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
                return {
                    'text': content,
                    'paragraphs': paragraphs,
                    'paragraph_count': len(paragraphs)
                }
        except Exception as e:
            raise Exception(f"Error reading TXT file: {str(e)}")

class EssayAnalyzer:
    def __init__(self):
        self.model = model
    
    def classify_essay_type(self, text):
        text_lower = text.lower()
        scores = {}
        
        for essay_type, data in ESSAY_TYPES.items():
            score = sum(1 for keyword in data['keywords'] if keyword in text_lower)
            scores[essay_type] = score
        
        primary_type = max(scores, key=scores.get) if scores else 'expository'
        high_scores = [t for t, s in scores.items() if s >= max(scores.values()) * 0.7] if scores else []
        
        return {
            'primary_type': primary_type,
            'hybrid_types': high_scores if len(high_scores) > 1 else [],
            'confidence': scores[primary_type] / len(ESSAY_TYPES[primary_type]['keywords']) if ESSAY_TYPES.get(primary_type, {}).get('keywords') else 0.5
        }
    
    def analyze_grammar_and_style(self, text):
        if not self.model:
            return self._fallback_analysis(text)
            
        prompt = f"""
        Please analyze the following essay for grammar, style, and structure issues. 
        Provide specific suggestions for improvement in JSON format with the following structure:
        {{
            "grammar_issues": [
                {{"issue": "description", "suggestion": "correction", "line": "approximate line number"}}
            ],
            "style_issues": [
                {{"issue": "description", "suggestion": "improvement", "line": "approximate line number"}}
            ],
            "structure_issues": [
                {{"issue": "description", "suggestion": "improvement", "section": "section name"}}
            ],
            "overall_score": "score out of 100",
            "strengths": ["list of strengths"],
            "priority_improvements": ["top 3 improvements needed"]
        }}
        
        Essay text:
        {text[:2000]}...
        """
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            else:
                return self._fallback_analysis(text)
        except Exception as e:
            print(f"Error in AI analysis: {e}")
            return self._fallback_analysis(text)
    
    def analyze_essay_specific_criteria(self, text, essay_type):
        if not self.model:
            return self._fallback_type_analysis(essay_type)
            
        criteria = ESSAY_TYPES.get(essay_type, {}).get('criteria', [])
        
        prompt = f"""
        Analyze this {essay_type} essay based on these specific criteria: {', '.join(criteria)}.
        Also check for source authenticity issues (like Wikipedia usage in argumentative essays).
        
        Provide analysis in JSON format:
        {{
            "criteria_analysis": [
                {{"criterion": "name", "score": "1-10", "feedback": "detailed feedback"}}
            ],
            "source_issues": [
                {{"issue": "description", "suggestion": "improvement"}}
            ],
            "type_specific_suggestions": ["list of suggestions specific to {essay_type} essays"]
        }}
        
        Essay text:
        {text[:2000]}...
        """
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            else:
                return self._fallback_type_analysis(essay_type)
        except Exception as e:
            print(f"Error in type-specific analysis: {e}")
            return self._fallback_type_analysis(essay_type)
    
    def generate_interactive_suggestions(self, text):
        if not self.model:
            return self._fallback_suggestions(text)
            
        words = text.split()
        chunk_size = 500
        all_suggestions = []
        
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)
            chunk_start_pos = len(' '.join(words[:i]))
            
            prompt = f"""
            Analyze the following essay excerpt and provide specific word-level and sentence-level suggestions for improvement.
            For each suggestion, provide the exact original text and the suggested replacement.
            
            Provide the response in JSON format:
            {{
                "suggestions": [
                    {{
                        "id": "unique_id_{i}",
                        "type": "grammar|spelling|style|structure",
                        "original": "exact original text to be replaced",
                        "suggested": "suggested replacement text",
                        "reason": "explanation for the change",
                        "position": {{
                            "start": start_character_position,
                            "end": end_character_position
                        }},
                        "severity": "high|medium|low"
                    }}
                ]
            }}
            
            Essay excerpt:
            {chunk_text}
            
            Focus on:
            1. Spelling errors
            2. Grammar mistakes
            3. Word choice improvements
            4. Sentence structure
            5. Clarity and flow
            """
            
            try:
                response = self.model.generate_content(prompt)
                response_text = response.text
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_str = response_text[json_start:json_end]
                    chunk_result = json.loads(json_str)
                    
                    for suggestion in chunk_result.get('suggestions', []):
                        suggestion['position']['start'] += chunk_start_pos
                        suggestion['position']['end'] += chunk_start_pos
                        suggestion['id'] = f"suggestion_{len(all_suggestions) + 1}"
                    
                    all_suggestions.extend(chunk_result.get('suggestions', []))
                    
            except Exception as e:
                print(f"Error processing chunk {i}: {e}")
                continue
        
        return {"suggestions": all_suggestions[:20]}
    
    def _fallback_analysis(self, text):
        word_count = len(text.split())
        return {
            "grammar_issues": [
                {"issue": "AI analysis temporarily unavailable", "suggestion": "Please check your API configuration", "line": "N/A"}
            ],
            "style_issues": [
                {"issue": "Manual review recommended", "suggestion": "Consider sentence variety and word choice", "line": "N/A"}
            ],
            "structure_issues": [
                {"issue": "Check essay organization", "suggestion": "Ensure clear introduction, body, and conclusion", "section": "Overall"}
            ],
            "overall_score": "75",
            "strengths": [
                f"Essay contains {word_count} words",
                "Content has been provided for analysis",
                "Structure appears to follow basic essay format"
            ],
            "priority_improvements": [
                "Configure AI API key for detailed analysis",
                "Review grammar and spelling manually",
                "Check essay structure and flow"
            ]
        }
    
    def _fallback_type_analysis(self, essay_type):
        return {
            "criteria_analysis": [
                {"criterion": f"{essay_type} structure", "score": "7", "feedback": "AI analysis unavailable - manual review recommended"},
                {"criterion": "Content relevance", "score": "8", "feedback": "Content appears relevant to essay type"},
                {"criterion": "Organization", "score": "7", "feedback": "Basic organization present"}
            ],
            "source_issues": [
                {"issue": "Unable to verify sources", "suggestion": "Manually check source credibility and citations"}
            ],
            "type_specific_suggestions": [
                f"Review {essay_type} essay guidelines and requirements",
                "Ensure all criteria for this essay type are met",
                "Consider peer review for additional feedback"
            ]
        }
    
    def _fallback_suggestions(self, text):
        suggestions = []
        if "i " in text.lower():
            suggestions.append({
                "id": "suggestion_1",
                "type": "style",
                "original": "i",
                "suggested": "I",
                "reason": "Capitalize the pronoun 'I'",
                "position": {"start": text.lower().find("i "), "end": text.lower().find("i ") + 1},
                "severity": "medium"
            })
        
        if text.count('.') < 3:
            suggestions.append({
                "id": "suggestion_2",
                "type": "structure",
                "original": "Short essay",
                "suggested": "Consider expanding with more detailed examples",
                "reason": "Essay appears to be quite short",
                "position": {"start": 0, "end": 0},
                "severity": "low"
            })
        
        return {"suggestions": suggestions}

# Initialize analyzer and processor
analyzer = EssayAnalyzer()
doc_processor = DocumentProcessor()


@csrf_exempt
@require_POST
def analyze_essay(request):
    try:
        data = json.loads(request.body)
        essay_text = data.get('text', '')
        
        if not essay_text.strip():
            return JsonResponse({'error': 'No essay text provided'}, status=400)
        
        if len(essay_text.strip()) < 50:
            return JsonResponse({'error': 'Essay is too short for meaningful analysis'}, status=400)
        
        classification = analyzer.classify_essay_type(essay_text)
        general_analysis = analyzer.analyze_grammar_and_style(essay_text)
        specific_analysis = analyzer.analyze_essay_specific_criteria(
            essay_text, classification['primary_type']
        )
        interactive_suggestions = analyzer.generate_interactive_suggestions(essay_text)
        
        results = {
            'classification': classification,
            'analysis': {
                'general': general_analysis,
                'specific': specific_analysis
            },
            'interactive_suggestions': interactive_suggestions,
            'timestamp': datetime.now().isoformat(),
            'word_count': len(essay_text.split()),
            'character_count': len(essay_text)
        }
        
        return JsonResponse(results)
        
    except Exception as e:
        print(f"Error in analysis: {e}")
        return JsonResponse({'error': f'Analysis failed: {str(e)}'}, status=500)

@csrf_exempt
@require_POST
def upload_file(request):
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'No file uploaded'}, status=400)
        
        uploaded_file = request.FILES['file'] # Renamed for clarity

        if uploaded_file.name == '':
            return JsonResponse({'error': 'No file selected'}, status=400)
        
        # Check file extension
        if not uploaded_file.name.lower().endswith(('.txt', '.docx')):
            return JsonResponse({'error': 'Unsupported file type. Please upload TXT or DOCX files.'}, status=400)
        
        # Sanitize filename if needed, but default_storage.save handles most of it
        filename = secure_filename(uploaded_file.name) # Use the sanitized name for saving
        
        # Create a temporary file path within the system's temp directory
        # This will be used only for reading the content, not for permanent storage via Django's storage system.
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_file_path = os.path.join(tmpdir, filename)
            
            # Write the uploaded file's chunks to the temporary file
            # This is safer than file.read() for large files as it avoids loading the whole file into memory
            with open(temp_file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)

            content = {}
            try:
                # Read content from the temporary file
                if filename.lower().endswith('.txt'):
                    content = doc_processor.read_txt(temp_file_path)
                else: # .docx
                    content = doc_processor.read_docx(temp_file_path)
                
                # The temporary directory and its contents are automatically cleaned up
                # when exiting the 'with' block, so no need for os.unlink(temp_file_path)
                
                return JsonResponse({
                    'text': content.get('text', ''),
                    'filename': filename,
                    'paragraphs': content.get('paragraphs', []),
                    'paragraph_count': content.get('paragraph_count', 0)
                })
                
            except Exception as e:
                # If an error occurs during file processing, it will be caught here
                return JsonResponse({'error': f'Error processing file content: {str(e)}'}, status=400)
        
    except Exception as e:
        print(f"Error in file upload: {e}")
        return JsonResponse({'error': f'File upload failed: {str(e)}'}, status=500)

@csrf_exempt
@require_POST
def download_revision(request):
    try:
        data = json.loads(request.body)
        final_text = data.get('final_text', '')
        title = data.get('title', 'Revised Essay')
        
        if not final_text:
            return JsonResponse({'error': 'No final text provided'}, status=400)
        
        doc = Document()
        title_para = doc.add_heading(title, 0)
        paragraphs = final_text.split('\n\n')
        for paragraph in paragraphs:
            if paragraph.strip():
                doc.add_paragraph(paragraph.strip())
        
        doc_io = io.BytesIO()
        doc.save(doc_io)
        doc_io.seek(0)
        
        response = HttpResponse(
            content=doc_io.read(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="{title.replace(" ", "_")}_final.docx"'
        return response
        
    except Exception as e:
        print(f"Error creating download: {e}")
        return JsonResponse({'error': 'Failed to create download'}, status=500)

@require_GET
def health_check(request):
    return JsonResponse({
        'status': 'healthy',
        'ai_available': model is not None,
        'timestamp': datetime.now().isoformat()
    })


# ... (existing imports) ...
import difflib # Ensure this is imported at the top of your file

# ... (existing DocumentProcessor and EssayAnalyzer classes) ...

class DocumentComparator:
    """
    Compares two text documents and highlights their differences.
    """
    def compare_documents(self, content1: Dict, content2: Dict, name1: str = "Document 1", name2: str = "Document 2") -> Dict:
        """
        Compares the text content of two documents and returns a detailed diff.

        Args:
            content1 (Dict): Dictionary containing 'text' key for the first document.
            content2 (Dict): Dictionary containing 'text' key for the second document.
            name1 (str): Name of the first document for display purposes.
            name2 (str): Name of the second document for display purposes.

        Returns:
            Dict: A dictionary containing the comparison results, including HTML diff.
        """
        text1 = content1.get('text', '').splitlines(keepends=True)
        text2 = content2.get('text', '').splitlines(keepends=True)

        d = difflib.HtmlDiff()
        html_diff = d.make_file(text1, text2, name1, name2)

        # You might also want to provide a more programmatic difference summary
        matcher = difflib.SequenceMatcher(None, text1, text2)
        diff_summary = {
            "ratio": matcher.ratio(), # Measures similarity (0.0 to 1.0)
            "opcodes": [] # List of (tag, i1, i2, j1, j2)
        }

        # Detailed opcodes for programmatic understanding of changes
        for opcode in matcher.get_opcodes():
            tag, i1, i2, j1, j2 = opcode
            diff_summary["opcodes"].append({
                "tag": tag, # 'replace', 'delete', 'insert', 'equal'
                "original_start": i1,
                "original_end": i2,
                "revised_start": j1,
                "revised_end": j2,
                "original_text_snippet": "".join(text1[i1:i2]).strip() if tag != 'insert' else "",
                "revised_text_snippet": "".join(text2[j1:j2]).strip() if tag != 'delete' else "",
            })

        return {
            "html_diff": html_diff,
            "summary": diff_summary,
            "diff_found": html_diff != d.make_file([], []) # Simple check if any diff exists
        }



@api_view(['POST'])
@parser_classes([MultiPartParser])
def compare_documents(request):
    try:
        file1 = request.FILES.get('file1')
        file2 = request.FILES.get('file2')

        if not file1 or not file2:
            return Response({'error': 'Two files are required for comparison'}, status=400)

        if file1.name == '' or file2.name == '':
            return Response({'error': 'Please select both files'}, status=400)

        allowed_extensions = ('.txt', '.docx')
        if not (file1.name.lower().endswith(allowed_extensions) and file2.name.lower().endswith(allowed_extensions)):
            return Response({'error': 'Both files must be TXT or DOCX format'}, status=400)

        # Save files temporarily
        filename1 = secure_filename(file1.name)
        filename2 = secure_filename(file2.name)
        temp_path1 = os.path.join(tempfile.gettempdir(), f"comp1_{filename1}")
        temp_path2 = os.path.join(tempfile.gettempdir(), f"comp2_{filename2}")

        with open(temp_path1, 'wb') as f1:
            for chunk in file1.chunks():
                f1.write(chunk)
        with open(temp_path2, 'wb') as f2:
            for chunk in file2.chunks():
                f2.write(chunk)

        try:
            # Read content
            if filename1.endswith('.txt'):
                content1 = doc_processor.read_txt(temp_path1)
            else:
                content1 = doc_processor.read_docx(temp_path1)

            if filename2.endswith('.txt'):
                content2 = doc_processor.read_txt(temp_path2)
            else:
                content2 = doc_processor.read_docx(temp_path2)

            comparison_results = DocumentComparator().compare_documents(
                content1, content2, filename1, filename2
            )

            return Response({
                'comparison': comparison_results,
                'file1_name': filename1,
                'file2_name': filename2,
                'timestamp': now().isoformat()
            }, status=200)

        except Exception as e:
            return Response({'error': f'Error processing files: {str(e)}'}, status=400)

        finally:
            for temp_path in [temp_path1, temp_path2]:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

    except Exception as e:
        print(f"Error in document comparison: {e}")
        return Response({'error': 'Document comparison failed'}, status=500)