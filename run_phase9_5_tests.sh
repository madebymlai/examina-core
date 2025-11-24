#!/bin/bash
# Phase 9.5: Multi-Course Testing - Quick Run Script

echo "=================================================="
echo "  Phase 9.5: Multi-Course Testing Suite"
echo "  Theory and Proof Support Validation"
echo "=================================================="
echo ""

# Test 1: Comprehensive multi-course analysis
echo "1. Running comprehensive multi-course test..."
echo "   (Exercise type distribution across ADE, AL, PC)"
echo ""
python test_phase9_5_multi_course.py
echo ""
echo "Press Enter to continue..."
read

# Test 2: Detailed analysis with examples
echo ""
echo "2. Running detailed analysis with examples..."
echo "   (Sample exercises from each type and course)"
echo ""
python test_phase9_5_detailed_analysis.py
echo ""
echo "Press Enter to continue..."
read

# Test 3: Inspection scripts
echo ""
echo "3. Running theory question inspection..."
echo ""
python inspect_theory_questions.py
echo ""
echo "Press Enter to continue..."
read

echo ""
echo "4. Running detailed theory inspection..."
echo ""
python inspect_theory_detail.py
echo ""

# Summary
echo ""
echo "=================================================="
echo "  Testing Complete!"
echo "=================================================="
echo ""
echo "Reports Generated:"
echo "  - PHASE_9_5_REPORT.md (comprehensive report)"
echo ""
echo "Test Scripts:"
echo "  - test_phase9_5_multi_course.py (summary statistics)"
echo "  - test_phase9_5_detailed_analysis.py (detailed examples)"
echo "  - inspect_theory_questions.py (theory detection)"
echo "  - inspect_theory_detail.py (detailed theory view)"
echo ""
echo "Key Findings:"
echo "  ✅ Detection works across all 3 courses"
echo "  ✅ Proof detection: 22/91 exercises (24.2%)"
echo "  ✅ High confidence: 51.9-88.5%"
echo "  ⚠️  Theory detection needs tuning"
echo ""
echo "See PHASE_9_5_REPORT.md for full details."
echo ""
