from domain.users import User

def load_user(user_id: str) -> User:
    return User(user_id)
