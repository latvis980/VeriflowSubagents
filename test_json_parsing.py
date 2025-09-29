# simple_analyzer_test.py
"""
Simple test for the FactAnalyzer component
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append('/app')  # For Railway
sys.path.append('.')     # For local

# Load environment variables
load_dotenv()

class Config:
    def __init__(self):
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set in environment")

async def test_analyzer():
    """Test the FactAnalyzer with simple input"""

    try:
        # Import after setting up path
        from agents.analyser import FactAnalyzer

        print("✅ Successfully imported FactAnalyzer")

        config = Config()
        analyzer = FactAnalyzer(config)

        print("✅ FactAnalyzer initialized")

        # Simple test data
        test_input = {
            'text': 'The Silo Hotel in Cape Town opened in 2017. It has 28 rooms.',
            'links': [
                {'url': 'https://example.com/silo-hotel', 'anchor_text': 'source1'}
            ],
            'format': 'chatgpt'
        }

        print("🔍 Testing fact analysis...")
        print(f"📝 Input text: {test_input['text']}")

        # Run the analyzer
        facts = await analyzer.analyze(test_input)

        print(f"✅ Analysis complete! Found {len(facts)} facts")

        for fact in facts:
            print(f"📊 Fact {fact.id}: {fact.statement}")
            print(f"   Sources: {fact.sources}")
            print(f"   Confidence: {fact.confidence}")
            print()

        return facts

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("🔍 Check your Python path and file locations")
        return None

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def test_prompts():
    """Test if prompts load correctly"""
    try:
        from prompts.analyzer_prompts import get_analyzer_prompts
        prompts = get_analyzer_prompts()

        print("✅ Prompts loaded successfully")
        print(f"📋 System prompt length: {len(prompts['system'])}")
        print(f"📋 User prompt length: {len(prompts['user'])}")
        print(f"📋 System prompt preview: {prompts['system'][:200]}...")

        return True

    except Exception as e:
        print(f"❌ Prompt loading failed: {e}")
        return False

async def main():
    """Run the tests"""
    print("🧪 Testing FactAnalyzer Component")
    print("=" * 50)

    # Test 1: Check prompts
    print("\n1️⃣ Testing prompt loading...")
    prompts_ok = await test_prompts()

    if not prompts_ok:
        print("❌ Prompts failed, skipping analyzer test")
        return

    # Test 2: Test analyzer
    print("\n2️⃣ Testing FactAnalyzer...")
    facts = await test_analyzer()

    if facts:
        print(f"🎉 Test successful! Extracted {len(facts)} facts")
    else:
        print("❌ Analyzer test failed")

if __name__ == "__main__":
    asyncio.run(main())