# System Architecture Diagrams

## Database Schema

```mermaid
erDiagram
    User ||--o{ Clip : creates
    User ||--o{ ClipAnnotation : creates
    
    Clip ||--o{ ClipAnnotation : contains
    Clip }o--o{ ClipTag : tagged_with
    Clip }o--o{ Player : features
    Clip }o--|| Game : belongs_to
    Clip }o--|| Point : belongs_to
    
    ClipAnnotation }o--o{ AnnotationTag : tagged_with
    ClipAnnotation }o--o{ Player : involves
    
    ClipTag ||--o{ ClipTag : parent_of
    AnnotationTag ||--o{ AnnotationTag : parent_of
    
    User {
        int id PK
        string username
        string email
        int team_organization_id FK
    }
    
    Clip {
        int id PK
        string title
        string youtube_link
        int start_time
        int end_time
        int game_id FK
        int point_id FK
        int created_by_id FK
        boolean is_featured
        int view_count
    }
    
    ClipTag {
        int id PK
        string name
        string category
        int parent_tag_id FK
        string color
        boolean is_active
    }
    
    ClipAnnotation {
        int id PK
        int clip_id FK
        int user_id FK
        int timestamp
        string title
        string event_type
        int our_score
        int their_score
        string offense
        string defense
        text notes
        boolean is_key_moment
        string visibility
    }
    
    AnnotationTag {
        int id PK
        string name
        string category
        int parent_tag_id FK
        string color
        boolean is_active
    }
    
    Player {
        int id PK
        string name
        int jersey_number
    }
    
    Game {
        int id PK
        string opponent
        date date
    }
```

## Tag Hierarchy Structure

```mermaid
graph TD
    A[Video Tags - ClipTag] --> B[Full Game]
    A --> C[Training Session]
    A --> D[Highlight Showcase]
    A --> E[Tournament Video]
    
    B --> B1[Our Team vs Opponent]
    B --> B2[Opponent vs Opponent]
    
    C --> C1[Drills Only]
    C --> C2[Scrimmage]
    C --> C3[Theme-Based Practice]
    
    F[Annotation Tags - AnnotationTag] --> G[Offense]
    F --> H[Defense]
    F --> I[Skills]
    F --> J[Situations]
    F --> K[Outcomes]
    
    G --> G1[Handler Movement]
    G --> G2[Cutting]
    G --> G3[Throw Types]
    
    G1 --> G1A[Reset]
    G1 --> G1B[Upline]
    G1 --> G1C[Give-and-Go]
    
    G2 --> G2A[Under Cut]
    G2 --> G2B[Deep Cut]
    G2 --> G2C[Break Side Cut]
    
    H --> H1[Person Defense]
    H --> H2[Zone Defense]
    H --> H3[Help & Switches]
    
    H1 --> H1A[Force Forehand]
    H1 --> H1B[Force Backhand]
    H1 --> H1C[Straight Up]
    
    style A fill:#3F51B5,color:#fff
    style F fill:#2196F3,color:#fff
    style G fill:#4CAF50,color:#fff
    style H fill:#F44336,color:#fff
```

## User Flow Diagram

```mermaid
flowchart TD
    Start([User Opens Clip Library]) --> Browse{Browse Mode}
    
    Browse -->|View Clips| ViewClip[View Clip Page]
    Browse -->|Add New| AddClip[Create New Clip]
    
    ViewClip --> WatchVideo[Watch Video]
    WatchVideo --> SeeAnnotations[View Annotations]
    
    SeeAnnotations --> Filter{Want to Filter?}
    Filter -->|Yes| ApplyFilters[Apply Filters]
    Filter -->|No| ClickTime[Click Timestamp]
    ApplyFilters --> ClickTime
    
    ClickTime --> JumpVideo[Video Jumps to Time]
    
    SeeAnnotations --> AddAnnotation{Add Annotation?}
    AddAnnotation -->|Yes| CreateForm[Fill Annotation Form]
    AddAnnotation -->|No| Continue[Continue Watching]
    
    CreateForm --> SelectTags[Select Tags]
    SelectTags --> TagPlayers[Tag Players]
    TagPlayers --> AddNotes[Add Notes]
    AddNotes --> SetVisibility[Set Visibility]
    SetVisibility --> KeyMoment{Key Moment?}
    KeyMoment -->|Yes| MarkKey[Mark as Key]
    KeyMoment -->|No| SaveAnnotation
    MarkKey --> SaveAnnotation[Save Annotation]
    
    SaveAnnotation --> RefreshView[Refresh Clip View]
    RefreshView --> SeeAnnotations
    
    AddClip --> UploadForm[Fill Clip Form]
    UploadForm --> SelectVideoTags[Select Video Type Tags]
    SelectVideoTags --> AssociateGame[Associate with Game]
    AssociateGame --> SaveClip[Save Clip]
    SaveClip --> ViewClip
```

## Annotation Creation Flow

```mermaid
sequenceDiagram
    participant User
    participant Browser
    participant Flask
    participant Database
    
    User->>Browser: Click "Add Annotation"
    Browser->>Flask: GET /clip/123/annotation/add
    Flask->>Database: Load Tags, Players
    Database->>Flask: Return data
    Flask->>Browser: Render form with choices
    Browser->>User: Display form
    
    User->>Browser: Fill form & submit
    Browser->>Flask: POST annotation data
    Flask->>Flask: Validate form
    Flask->>Database: Create ClipAnnotation
    Flask->>Database: Associate tags (many-to-many)
    Flask->>Database: Associate players (many-to-many)
    Database->>Flask: Confirm save
    Flask->>Browser: Redirect to clip view
    Browser->>User: Show updated annotations
```

## Permission Model

```mermaid
graph LR
    A[User Role] --> B{Check Permission}
    
    B -->|Admin| C[Full Access]
    B -->|Coach| D[Create, Edit Own, Delete Own]
    B -->|Player| E[Create, Edit Own, View All]
    
    C --> F[Can delete any annotation]
    C --> G[Can edit any annotation]
    C --> H[Can manage tags]
    
    D --> I[Can delete own annotations]
    D --> J[Can edit own annotations]
    D --> K[Can view all based on visibility]
    
    E --> L[Can delete own annotations]
    E --> M[Can edit own annotations]
    E --> N[Can view: Team + Own Private]
    
    N --> O{Visibility Check}
    O -->|Team| P[Show to everyone]
    O -->|Coaches| Q[Show to coaches/admins only]
    O -->|Private| R[Show to creator only]
    
    style C fill:#4CAF50
    style D fill:#2196F3
    style E fill:#FFC107
```

## Tag Organization Example

```mermaid
mindmap
  root((Annotation Tags))
    Offense
      Handler Movement
        Reset
        Upline
        Give-and-Go
      Cutting
        Under Cut
        Deep Cut
        Break Side
      Throw Types
        Backhand
        Forehand
        Hammer
      Set Plays
        Ho Stack
        Vert Stack
        Split Stack
    Defense
      Person D
        Force FH
        Force BH
        Straight Up
      Zone D
        Cup
        Wall
        Junk
      Help
        Poach
        Switch
    Skills
      Throwing
        IO
        OI
        Break
        Huck
      Catching
        Layout
        High Point
```

## Data Flow: From Upload to Analysis

```mermaid
graph TB
    A[Game Day] --> B[Record Video]
    B --> C[Upload to YouTube/Veo]
    C --> D[Create Clip in System]
    D --> E[Tag Video Type]
    E --> F[Associate with Game/Point]
    
    F --> G[Film Session]
    G --> H[Watch & Discuss]
    H --> I[Add Annotations]
    
    I --> J[Tag Tactics]
    I --> K[Tag Players]
    I --> L[Add Coaching Notes]
    
    J --> M[Analysis]
    K --> M
    L --> M
    
    M --> N{Filter & Review}
    N --> O[By Player]
    N --> P[By Tactic]
    N --> Q[By Outcome]
    N --> R[Key Moments Only]
    
    O --> S[Individual Development]
    P --> T[Team Strategy]
    Q --> U[Performance Metrics]
    R --> V[Highlight Reel]
    
    style A fill:#FFE082
    style G fill:#90CAF9
    style M fill:#A5D6A7
    style S fill:#CE93D8
    style T fill:#CE93D8
    style U fill:#CE93D8
    style V fill:#CE93D8
```

## Component Interaction

```mermaid
graph TD
    subgraph Frontend
        A[View Clip Template]
        B[Annotation Form]
        C[Filter Controls]
    end
    
    subgraph Backend Routes
        D[clip.view_clip]
        E[clip.add_annotation]
        F[clip.edit_annotation]
        G[clip.delete_annotation]
    end
    
    subgraph Forms
        H[AnnotationForm]
        I[QuickAnnotationForm]
        J[AnnotationFilterForm]
    end
    
    subgraph Models
        K[Clip]
        L[ClipAnnotation]
        M[AnnotationTag]
        N[User]
        O[Player]
    end
    
    subgraph Database
        P[(PostgreSQL/SQLite)]
    end
    
    A --> D
    B --> E
    C --> D
    
    D --> K
    E --> H
    E --> L
    F --> H
    F --> L
    G --> L
    
    H --> M
    H --> O
    I --> M
    J --> M
    
    K --> P
    L --> P
    M --> P
    N --> P
    O --> P
```

---

## Key Relationships

### One-to-Many
- User → Clips (one user creates many clips)
- User → Annotations (one user creates many annotations)
- Clip → Annotations (one clip has many annotations)
- Game → Clips (one game has many clips)

### Many-to-Many
- Clip ↔ ClipTag (clips can have multiple video tags)
- Clip ↔ Player (clips can feature multiple players)
- Annotation ↔ AnnotationTag (annotations can have multiple tactical tags)
- Annotation ↔ Player (annotations can involve multiple players)

### Self-Referential
- ClipTag → ClipTag (hierarchical parent-child)
- AnnotationTag → AnnotationTag (hierarchical parent-child)

---

These diagrams can be viewed using any Mermaid renderer:
- GitHub (renders automatically)
- Mermaid Live Editor (https://mermaid.live)
- VS Code with Mermaid extension
- Many documentation platforms
