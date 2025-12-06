import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.yandex_client import yandex_gpt_client

@pytest.mark.asyncio
async def test_ai_tool_call_parsing():
    # 1. Подделываем ответ от Яндекса (как будто он прислал JSON с инструментом)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {
            "alternatives": [{
                "message": {
                    "role": "assistant",
                    "toolCallList": {
                        "toolCalls": [{
                            "functionCall": {
                                "name": "create_appointment",
                                "arguments": {
                                    "service_name": "стрижка",
                                    "appointment_date": "2025-12-08",
                                    "appointment_time": "15:00"
                                }
                            }
                        }]
                    }
                },
                "status": "ALTERNATIVE_STATUS_TOOL_CALLS"
            }]
        }
    }

    # 2. Подменяем реальный httpx клиент нашим фейковым
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        # Подделываем state (FSMContext)
        mock_state = AsyncMock()
        mock_state.get_data.return_value = {"chat_history": []}

        # 3. Вызываем нашу функцию
        result = await yandex_gpt_client.generate_response_or_tool_call(
            state=mock_state,
            user_message="Запиши на стрижку",
            user_name="TestUser"
        )

        # 4. Проверяем, что код правильно понял ответ Яндекса
        assert result["type"] == "tool_call"
        assert result["name"] == "create_appointment"
        assert result["args"]["service_name"] == "стрижка"
        assert result["args"]["appointment_time"] == "15:00"
