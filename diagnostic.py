#!/usr/bin/env python3
"""
Script de diagnóstico para el sistema de voz JARVIS
"""

import requests
import json
import base64
import time
import sys

def test_health():
    """Prueba el endpoint /health"""
    print("🔍 Probando /health...")
    try:
        resp = requests.get("http://localhost:8000/health", timeout=5)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Estado: {data.get('state')}")
            print(f"   OK: {data.get('ok')}")
            print(f"   Último error: {data.get('last_error')}")
            return True
        else:
            print(f"   Error: {resp.text}")
            return False
    except Exception as e:
        print(f"   Excepción: {e}")
        return False

def test_state():
    """Prueba el endpoint /state"""
    print("\n🔍 Probando /state...")
    try:
        resp = requests.get("http://localhost:8000/state", timeout=5)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Session ID: {data.get('session_id')}")
            print(f"   Ready: {data.get('ready')}")
            print(f"   Status: {data.get('status')}")
            return True
        else:
            print(f"   Error: {resp.text}")
            return False
    except Exception as e:
        print(f"   Excepción: {e}")
        return False

def test_chat(text="Hola, ¿cómo estás?"):
    """Prueba el endpoint /chat"""
    print(f"\n💬 Probando /chat con mensaje: '{text}'")
    try:
        payload = {"text": text}
        resp = requests.post("http://localhost:8000/chat", json=payload, timeout=30)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   OK: {data.get('ok')}")
            if data.get('ok'):
                print(f"   Respuesta: {data.get('reply_text', '')[:100]}...")
                audio_b64 = data.get('audio_base64', '')
                if audio_b64:
                    print(f"   Audio: {len(audio_b64)} bytes base64")
                else:
                    print(f"   Audio: NO generado")
                return True
            else:
                print(f"   Error: {data.get('error')}")
                return False
        else:
            print(f"   Error HTTP: {resp.text}")
            return False
    except Exception as e:
        print(f"   Excepción: {e}")
        return False

def test_openclaw_hook():
    """Prueba directamente el hook de OpenClaw"""
    print("\n🔌 Probando hook de OpenClaw directamente...")
    try:
        # Primero obtenemos un session_id del estado
        resp = requests.get("http://localhost:8000/state", timeout=5)
        if resp.status_code != 200:
            print("   No se pudo obtener session_id")
            return False
            
        data = resp.json()
        session_id = data.get('session_id')
        print(f"   Session ID: {session_id}")
        
        # Probamos el hook directamente
        hook_url = "http://127.0.0.1:18789/hook"
        payload = {
            "sessionKey": session_id,
            "text": "Prueba de diagnóstico",
            "clientMessageId": f"test-{int(time.time())}"
        }
        
        print(f"   Enviando a: {hook_url}")
        resp = requests.post(hook_url, json=payload, timeout=10)
        print(f"   Status: {resp.status_code}")
        print(f"   Respuesta: {resp.text[:200]}...")
        
        return resp.status_code == 200
    except Exception as e:
        print(f"   Excepción: {e}")
        return False

def check_openclaw_status():
    """Verifica el estado de OpenClaw Gateway"""
    print("\n⚙️ Verificando OpenClaw Gateway...")
    try:
        # Verificar dashboard
        resp = requests.get("http://127.0.0.1:18789/", timeout=5)
        print(f"   Dashboard: {'Accesible' if resp.status_code == 200 else 'Inaccesible'}")
        
        # Verificar API
        resp = requests.get("http://127.0.0.1:18789/api/status", timeout=5)
        print(f"   API Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Versión: {data.get('version')}")
            print(f"   Uptime: {data.get('uptime')}")
            return True
        return False
    except Exception as e:
        print(f"   Excepción: {e}")
        return False

def main():
    print("=" * 60)
    print("DIAGNÓSTICO DEL SISTEMA DE VOZ JARVIS")
    print("=" * 60)
    
    # Verificar que el servidor esté corriendo
    print("\n📡 Verificando servidor local...")
    try:
        resp = requests.get("http://localhost:8000/", timeout=5)
        if resp.status_code == 200:
            print("✅ Servidor JARVIS está corriendo")
        else:
            print(f"❌ Servidor responde con código: {resp.status_code}")
            print("   Ejecuta: cd ~/jarvislab/mic && ./start.sh")
            return
    except:
        print("❌ Servidor JARVIS no está corriendo")
        print("   Ejecuta: cd ~/jarvislab/mic && ./start.sh")
        return
    
    # Ejecutar pruebas
    tests = [
        ("Health Check", test_health),
        ("State Check", test_state),
        ("OpenClaw Gateway", check_openclaw_status),
        ("OpenClaw Hook", test_openclaw_hook),
        ("Chat Test 1", lambda: test_chat("Hola")),
        ("Chat Test 2", lambda: test_chat("¿Cuál es tu nombre?")),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n{'='*40}")
        print(f"Prueba: {name}")
        print(f"{'='*40}")
        try:
            success = test_func()
            results.append((name, success))
            print(f"Resultado: {'✅ PASÓ' if success else '❌ FALLÓ'}")
        except Exception as e:
            print(f"Error en prueba: {e}")
            results.append((name, False))
            print(f"Resultado: ❌ FALLÓ")
    
    # Resumen
    print(f"\n{'='*60}")
    print("RESUMEN DE DIAGNÓSTICO")
    print(f"{'='*60}")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}")
    
    print(f"\nTotal: {passed}/{total} pruebas pasaron")
    
    if passed < total:
        print("\n🔧 RECOMENDACIONES:")
        print("1. Verifica que OpenClaw Gateway esté corriendo: openclaw gateway status")
        print("2. Revisa los logs: tail -f ~/jarvislab/mic/logs/bridge.jsonl")
        print("3. Verifica la configuración de hooks en ~/.openclaw/openclaw.json")
        print("4. Reinicia el sistema: killall uvicorn && cd ~/jarvislab/mic && ./start.sh")

if __name__ == "__main__":
    main()