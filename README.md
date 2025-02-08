# MOBILE LEGENDS DRAFT PICK SUPPORT SYSTEM
Mobile legends draft pick decision support system which originally by [R-N/ml_draftpick_dss](https://github.com/R-N/ml_draftpick_dss).

# How To Use
Simply add `import ml_draftpick_dss.<class to be import>` to your app. Here is full example:

### Get Latest Hero List
```py
import ml_draftpick_dss.scraping.hero_list

def main():
    hero_list = ml_draftpick_dss.scraping.hero_list.scrap()
    print(f"Got hero list: {hero_list}")


if __name__ == '__main__':
    main()
```

### Get Hero Skills as List
```py
import ml_draftpick_dss.scraping.hero_skills

def main():
    hero_skills_list = ml_draftpick_dss.scraping.hero_skills.scrap_all()
    print(f"Got hero skills list: {hero_skills_list}")


if __name__ == '__main__':
    main()
```

# Limitation
Currently, for predicting draft pick there is no example because im beginner in Machine Learning. Otherwise, you can help me to contribute to this project.