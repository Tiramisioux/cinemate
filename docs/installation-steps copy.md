```mermaid
%%{init: {"theme":"base",
          "themeVariables":{
              "primaryColor":"#2980b9",
              "secondaryColor":"#e7f2fa",
              "tertiaryColor":"#f5f5f5",
              "fontFamily":"Roboto, Arial, sans-serif"}} }%%

graph TD
    Sensor["Camera Sensor"]:::component
    Pi["Raspberry Pi SoC"]:::component
    Libcamera["libcamera (1.7.0)"]:::component
    CinePi["cinepi-raw (C++)"]:::component
    RedisKV["Redis Key‑Value Store"]:::redis
    Cinemate["Cinemate (Python UI)"]:::ui

    Sensor --> Pi
    Pi --> Libcamera
    Libcamera --> CinePi
    RedisKV --> CinePi
    Cinemate <--> RedisKV

    classDef component fill:#ffffff,stroke:#2980b9,color:#2980b9;
    classDef redis fill:#ffd43b,stroke:#2980b9,color:#000;
    classDef ui fill:#c6e48b,stroke:#2980b9,color:#000;
```


{==

Formatting can also be applied to blocks by putting the opening and closing
tags on separate lines and adding new lines between the tags and the content.

==}

    :::{tip}
    Let's give readers a helpful hint!
    :::

```bash
This is my note
```

```mermaid
graph TD
  DSLR["Camera Body"] -->|HDMI| Pi[Pi 4B]
  Pi -->|USB| SSD
```

```mermaid
%%{ init: {
     "theme": "base",                       /* ← only “base” can be customised */
     "themeVariables": {
       "background": "#603e3eff"              /* ① canvas colour */
     }
   }
}%%

graph TD
    %% ② either give each node a one-off style…
    Sensor["Camera Sensor"]
    style Sensor fill:#fff8e1,stroke:#c9a60a,stroke-width:2px,color:#333

    Pi["Raspberry Pi SoC"]
    style Pi fill:#e1f5fe,stroke:#0288d1,stroke-width:2px

    Libcamera["libcamera (1.7.0)"]
    style Libcamera fill:#ede7f6,stroke:#673ab7,stroke-width:2px

    %% …or assign them to a reusable class
    CinePi["CinePi-RAW (C++)"]:::code
    RedisKV["Redis Key-Value Store"]:::code
    Cinemate["Cinemate (Python UI)"]:::code

    classDef code fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#000;

    Sensor --> Pi
    Pi --> Libcamera
    Libcamera --> CinePi
    CinePi <--> RedisKV
    Cinemate <--> RedisKV
```

```pddl
def bubble_sort(items):
    for i in range(len(items)):
        for j in range(len(items) - 1 - i):
            if items[j] > items[j + 1]:
                items[j], items[j + 1] = items[j + 1], items[j]
```

``` py hl_lines="2 3"
def bubble_sort(items):
    for i in range(len(items)):
        for j in range(len(items) - 1 - i):
            if items[j] > items[j + 1]:
                items[j], items[j + 1] = items[j + 1], items[j]
```

`#!math p(x|y) = \frac{p(y|x)p(x)}{p(y)}`

:::python
    # Code goes here ...

:::python hl_lines="1 3"
    # This line is emphasized
    # This line isn't
    # This line is emphasized

```python
    print('hellow world')
```

```

Text can be {--deleted--} and replacement text {++added++}. This can also be
combined into {~~one~>a single~~} operation. {==Highlighting==} is also
possible {>>and comments can be added inline<<}.

hellow world')
```