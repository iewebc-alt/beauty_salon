{ pkgs, ... }: {
  # Канал обновлений
  channel = "stable-24.05";

  # Список пакетов для установки
  packages = [
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.docker
    pkgs.docker-compose
  ];

  # Переменные окружения
  env = {};

  idx = {
    extensions = [
      "ms-python.python"
    ];
    workspace = {
      onCreate = {
        setup-venv = "python -m venv venv && source venv/bin/activate && pip install -r requirements.txt";
      };
    };
  };
  
  # !!! ВОТ ЭТА СТРОКА САМАЯ ВАЖНАЯ - ОНА ВКЛЮЧАЕТ DOCKER !!!
  services.docker.enable = true;
}